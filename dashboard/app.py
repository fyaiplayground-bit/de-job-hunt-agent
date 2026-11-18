"""The dashboard (decision #41): applications sent and where each stands (#57), skill demand,
coverage, the application funnel and pipeline health.

    uv run streamlit run dashboard/app.py

It only reads the dbt marts, so what it shows always matches the daily report. Labels are in
English because this is the part of the portfolio an interviewer might open.
"""

import sys
from pathlib import Path

import altair as alt
import pandas as pd
import psycopg
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dashboard.queries import load_all  # noqa: E402

BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"  # validated categorical slots 1, 2, 3
STATUS_COLOR = {"Have": BLUE, "Not covered": ORANGE, "Learning": AQUA}
STATUS_LABEL = {"have": "Have", "not_covered": "Not covered", "learning": "Learning"}
ARCHETYPE_LABEL = {
    "analytics_engineer": "Analytics engineer",
    "pipeline_de": "Pipeline DE",
    "infra_de": "Infrastructure DE",
}
PERIOD_LABEL = {
    "today": "Today",
    "last_7_days": "Last 7 days",
    "prior_7_days": "Prior 7 days",
    "last_30_days": "Last 30 days",
}
TOP_SKILLS = 15
BAR_SIZE = 18
BAR_STEP = 28  # the space each bar gets, so no chart squeezes its labels away


def share(value: float | None) -> str:
    return "n/a" if value is None or pd.isna(value) else f"{value:.0%}"


def horizontal_bars(
    frame: pd.DataFrame,
    label: str,
    value: str,
    value_title: str,
    tooltip: list[alt.Tooltip],
    color: alt.Color | str = BLUE,
    value_format: str = "d",
) -> alt.LayerChart:
    """Ranked horizontal bars, largest first, with each bar's value beside it."""
    order = list(frame[label])
    y = alt.Y(f"{label}:N", sort=order, title=None, axis=alt.Axis(labelLimit=260, ticks=False))
    x = alt.X(
        f"{value}:Q", title=value_title,
        axis=alt.Axis(grid=True, gridColor="#ececea", tickCount=6),
    )
    encoded = {"color": color} if not isinstance(color, str) else {}
    mark = alt.Chart(frame).mark_bar(
        size=BAR_SIZE,
        cornerRadiusTopRight=4,
        cornerRadiusBottomRight=4,
        **({"color": color} if isinstance(color, str) else {}),
    )
    bars = mark.encode(x=x, y=y, tooltip=tooltip, **encoded)
    text = (
        alt.Chart(frame)
        .mark_text(align="left", dx=5, color="#52514e")
        .encode(x=x, y=y, text=alt.Text(f"{value}:Q", format=value_format))
    )
    return (bars + text).properties(height=alt.Step(BAR_STEP))


def daily_columns(
    frame: pd.DataFrame, value: str, title: str, value_format: str = "d"
) -> alt.Chart:
    return (
        alt.Chart(frame)
        .mark_bar(size=BAR_SIZE, color=BLUE, cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
        .encode(
            x=alt.X(
                "day:N", sort=list(frame["day"]), title=None,
                axis=alt.Axis(labelAngle=0, ticks=False),
            ),
            y=alt.Y(f"{value}:Q", title=title, axis=alt.Axis(gridColor="#ececea")),
            tooltip=[
                alt.Tooltip("day:N", title="Day"),
                alt.Tooltip(f"{value}:Q", title=title, format=value_format),
            ],
        )
        .properties(height=240)
    )


def overview(tables: dict[str, pd.DataFrame], is_sample: bool) -> None:
    coverage = tables["coverage"].set_index("period")
    month = coverage.loc["last_30_days"]
    funnel = tables["funnel"].set_index("stage")
    columns = st.columns(4)
    columns[0].metric(
        "Coverage, 30 days",
        share(month["coverage_share"]),
        help="Share of scored postings where the profile's skills clear the 50% must-have bar.",
    )
    columns[1].metric("Worth applying", int(funnel.loc["Worth applying", "jobs_real"]))
    columns[2].metric("DE jobs found", f"{int(funnel.loc['DE jobs found', 'jobs_real']):,}")
    columns[3].metric("AI cost so far", f"${tables['costs']['cost_usd'].sum():.2f}")
    briefed = int(funnel.loc["Briefed by AI", "jobs_real"])
    note = f"Coverage and skills rest on the {briefed} postings AI has briefed so far."
    if is_sample:
        note += " Scores are for a fictional sample profile, not a real candidate."
    st.caption(note)


def skills_tab(tables: dict[str, pd.DataFrame]) -> None:
    skills = tables["skills"].head(TOP_SKILLS).copy()
    if skills.empty:
        st.info("No briefed postings yet.")
        return
    skills["Status"] = skills["status"].map(STATUS_LABEL)
    skills["share_percent"] = skills["must_have_share"] * 100
    total = int(skills["jobs_30d"].iloc[0])
    st.subheader(f"Most requested must-have skills, last 30 days ({total} postings)")
    color = alt.Color(
        "Status:N",
        scale=alt.Scale(domain=list(STATUS_COLOR), range=list(STATUS_COLOR.values())),
        legend=alt.Legend(orient="top", title=None),
    )
    tooltip = [
        alt.Tooltip("skill_name:N", title="Skill"),
        alt.Tooltip("must_have_jobs:Q", title="Postings asking"),
        alt.Tooltip("share_percent:Q", title="Share, %", format=".0f"),
        alt.Tooltip("Status:N"),
    ]
    st.altair_chart(
        horizontal_bars(
            skills,
            "skill_name",
            "must_have_jobs",
            "Postings listing it as a must-have",
            tooltip,
            color,
        ),
        width="stretch",
    )
    with st.expander("Table"):
        st.dataframe(
            skills[["skill_name", "Status", "must_have_jobs", "nice_jobs", "trend"]].rename(
                columns={
                    "skill_name": "Skill",
                    "must_have_jobs": "Must-have postings",
                    "nice_jobs": "Nice-to-have postings",
                    "trend": "Trend",
                }
            ),
            hide_index=True,
        )


def coverage_tab(tables: dict[str, pd.DataFrame]) -> None:
    coverage = tables["coverage"]
    st.subheader("Share of postings the profile covers")
    columns = st.columns(len(coverage))
    for column, row in zip(columns, coverage.itertuples(), strict=True):
        column.metric(PERIOD_LABEL[row.period], share(row.coverage_share))
        column.caption(f"{row.jobs_clearing_bar} of {row.jobs_scored} postings")
    versions = coverage.loc[coverage["period"] == "last_30_days", "brief_versions"].iloc[0]
    if versions:
        st.caption(f"Read by prompt versions: {versions}.")
    archetypes = tables["archetypes"].copy()
    if archetypes.empty:
        return
    st.subheader("By role type, last 30 days")
    archetypes["Role"] = archetypes["archetype"].map(ARCHETYPE_LABEL)
    archetypes["percent"] = archetypes["coverage_share"] * 100
    archetypes = archetypes.sort_values("percent", ascending=False)
    tooltip = [
        alt.Tooltip("Role:N"),
        alt.Tooltip("percent:Q", title="Coverage, %", format=".0f"),
        alt.Tooltip("jobs_scored:Q", title="Postings"),
        alt.Tooltip("average_score:Q", title="Average score"),
    ]
    st.altair_chart(
        horizontal_bars(archetypes, "Role", "percent", "Coverage, %", tooltip, value_format=".0f"),
        width="stretch",
    )


def funnel_tab(tables: dict[str, pd.DataFrame], is_sample: bool) -> None:
    funnel = tables["funnel"].copy()
    st.subheader("From found to offer")
    if is_sample:
        funnel["jobs"] = funnel["jobs_real"] + funnel["jobs_sample"]
        st.caption(
            "Queued and Approved are sample-profile practice runs. "
            "Code refuses to mark a fictional resume as applied."
        )
    else:
        funnel["jobs"] = funnel["jobs_real"]
        if funnel["jobs_sample"].sum() > 0:
            st.caption("Real jobs only; the table also counts the sample-profile practice runs.")
    last = funnel[funnel["jobs"] > 0]["stage_order"].max()
    shown = funnel[funnel["stage_order"] <= max(7, last)]  # interview stages once one is reached
    tooltip = [alt.Tooltip("stage:N", title="Stage"), alt.Tooltip("jobs:Q", title="Jobs")]
    chart = horizontal_bars(shown, "stage", "jobs", "Jobs", tooltip)
    st.altair_chart(chart, width="stretch")
    with st.expander("Table"):
        st.dataframe(
            funnel[["stage", "jobs_real", "jobs_sample"]].rename(
                columns={"stage": "Stage", "jobs_real": "Real", "jobs_sample": "Sample profile"}
            ),
            hide_index=True,
        )


STATUS_TEXT = {
    "awaiting_approval": "Waiting for approval",
    "approved": "Approved, not sent",
    "passed": "Passed",
    "applied": "Applied, no reply yet",
    "recruiter_screen": "Recruiter screen",
    "tech_screen": "Tech screen",
    "onsite": "Onsite",
    "offer": "Offer",
    "rejected": "Rejected",
    "ghosted": "Ghosted",
    "withdrawn": "Withdrawn",
}
INTERVIEW_STATUSES = ("recruiter_screen", "tech_screen", "onsite")


def status_text(row: pd.Series) -> str:
    """The status as words; an application silent too long says so (decision #57)."""
    if row["silent"]:
        return f"No reply in {int(row['days_in_status'])} days"
    return STATUS_TEXT.get(row["status"], row["status"])


def applications_tab(tables: dict[str, pd.DataFrame]) -> None:
    apps = tables["applications"].copy()
    sent = apps[apps["applied_at"].notna()].copy()
    st.subheader("Applications")
    if sent.empty:
        st.info("Nothing sent yet. Applications appear here once they are marked applied.")
    else:
        columns = st.columns(5)
        columns[0].metric("Sent", len(sent))
        columns[1].metric("Interviewing", int(sent["status"].isin(INTERVIEW_STATUSES).sum()))
        columns[2].metric("Offers", int((sent["status"] == "offer").sum()))
        columns[3].metric("Rejected", int((sent["status"] == "rejected").sum()))
        columns[4].metric("No reply 21+ days", int(sent["silent"].sum()))
        sent["status_text"] = sent.apply(status_text, axis=1)
        st.dataframe(
            sent[
                ["applied_on", "company", "title", "score", "status_text", "days_in_status",
                 "location", "url"]
            ],
            column_config={
                "applied_on": "Applied",
                "company": "Company",
                "title": "Job",
                "score": st.column_config.NumberColumn("Fit", format="%d"),
                "status_text": "Status",
                "days_in_status": st.column_config.NumberColumn("Days in status", format="%d"),
                "location": "Location",
                "url": st.column_config.LinkColumn("Posting", display_text="open"),
            },
            hide_index=True,
            width="stretch",
        )
        st.caption(
            "Status changes are recorded with `agents.application_queue track`; "
            "no reply after 21 days is worked out from the dates, not recorded."
        )
    not_sent = apps[apps["applied_at"].isna()].copy()
    if not not_sent.empty:
        with st.expander(f"Queued but not sent ({len(not_sent)})"):
            not_sent["status_text"] = not_sent["status"].map(STATUS_TEXT)
            st.dataframe(
                not_sent[["batch_date", "company", "title", "score", "status_text", "reason"]],
                column_config={
                    "batch_date": "Batch", "company": "Company", "title": "Job",
                    "score": "Fit", "status_text": "Status", "reason": "Why",
                },
                hide_index=True,
                width="stretch",
            )


def pipeline_tab(tables: dict[str, pd.DataFrame]) -> None:
    pipeline = tables["pipeline"].copy()
    if pipeline.empty:
        st.info("No daily runs yet.")
        return
    pipeline["day"] = pd.to_datetime(pipeline["local_date"]).dt.strftime("%b %d")
    left, right = st.columns(2)
    with left:
        st.subheader("New DE jobs per day")
        st.altair_chart(
            daily_columns(pipeline, "new_de_jobs", "New DE jobs"), width="stretch"
        )
    with right:
        st.subheader("AI cost per day, USD")
        st.altair_chart(
            daily_columns(pipeline, "ai_cost_usd", "USD", ".2f"), width="stretch"
        )
    st.subheader("Daily runs")
    st.dataframe(
        pipeline[
            [
                "local_date",
                "last_status",
                "runs",
                "new_jobs",
                "new_de_jobs",
                "jobs_briefed",
                "jobs_over_cap",
                "failed_sources",
                "run_minutes",
                "ai_cost_usd",
            ]
        ].rename(
            columns={
                "local_date": "Day",
                "last_status": "Last status",
                "runs": "Runs",
                "new_jobs": "New jobs",
                "new_de_jobs": "New DE jobs",
                "jobs_briefed": "Briefed",
                "jobs_over_cap": "Over the cap",
                "failed_sources": "Failed sources",
                "run_minutes": "Minutes",
                "ai_cost_usd": "AI cost, USD",
            }
        ),
        hide_index=True,
    )


def main() -> None:
    st.set_page_config(page_title="Job Hunt Pipeline", layout="wide")
    st.title("Job Hunt Pipeline")
    try:
        tables = load_all()
    except psycopg.Error as exc:
        st.error(
            "Can't read the analytics tables. Is Postgres running, and has "
            f"`uv run python -m pipeline.analytics` been run?\n\n{exc}"
        )
        return
    queued = tables["funnel"].set_index("stage").loc["Queued"]
    # Only sample-profile practice batches so far: since the real profile went live (Milestone 5),
    # its queue holds real jobs and the scores are FL's.
    is_sample = int(queued["jobs_sample"]) > 0 and int(queued["jobs_real"]) == 0
    overview(tables, is_sample)
    applications, skills, coverage, funnel, pipeline = st.tabs(
        ["Applications", "Skills", "Coverage", "Funnel", "Pipeline"]
    )
    with applications:
        applications_tab(tables)
    with skills:
        skills_tab(tables)
    with coverage:
        coverage_tab(tables)
    with funnel:
        funnel_tab(tables, is_sample)
    with pipeline:
        pipeline_tab(tables)


main()
