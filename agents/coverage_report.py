"""The skill coverage report (Agent 9, decision #41): do the profile's skills cover the jobs?

Pure code on top of the dbt marts, no LLM. It reports where the candidate stands and never says
what to study (decision #13). Every figure carries how many postings stand behind it, because
only AI-briefed postings count and there are few of them at first.
"""

from typing import Any

import psycopg

TOP_SKILLS = 10
MIN_COMPARE_JOBS = 20  # below this, a change from last week means nothing
STATUS_LABEL = {"have": "已有", "learning": "在学", "not_covered": "没覆盖"}
TREND_LABEL = {"up": "↑", "down": "↓", "flat": "→", "not_enough_data": "数据不够"}
ARCHETYPE_LABEL = {
    "analytics_engineer": "分析工程师",
    "pipeline_de": "数据管道 DE",
    "infra_de": "偏基础设施 DE",
}


def _rows(conn: psycopg.Connection, query: str) -> list[dict[str, Any]]:
    with conn.cursor() as cursor:
        cursor.execute(query)
        names = [column.name for column in cursor.description]
        return [dict(zip(names, map(_plain, row), strict=True)) for row in cursor.fetchall()]


def _plain(value: Any) -> Any:
    """Plain numbers, so the result can be stored as JSON with the day's summary."""
    return float(value) if type(value).__name__ == "Decimal" else value


def read_coverage(conn: psycopg.Connection) -> dict[str, Any]:
    return {
        "periods": {
            row["period"]: row
            for row in _rows(conn, "select * from analytics_marts.mart_coverage_summary")
        },
        "archetypes": _rows(
            conn,
            "select archetype, jobs_scored, coverage_share"
            " from analytics_marts.mart_coverage_by_archetype order by jobs_scored desc",
        ),
        "top_skills": _rows(
            conn,
            "select skill_name, status, must_have_jobs, must_have_share, jobs_30d, trend"
            " from analytics_marts.mart_skill_frequency"
            f" order by rank limit {TOP_SKILLS}",
        ),
    }


def _share(period: dict[str, Any]) -> str:
    if not period["jobs_scored"]:
        return "还没有数据"
    share = period["coverage_share"]
    return f"{share:.0%}（{period['jobs_scored']} 个里 {period['jobs_clearing_bar']} 个）"


def _change(week: dict[str, Any], prior: dict[str, Any]) -> str:
    if week["jobs_scored"] < MIN_COMPARE_JOBS or prior["jobs_scored"] < MIN_COMPARE_JOBS:
        return f"数据不够（上周 {prior['jobs_scored']} 个，至少要 {MIN_COMPARE_JOBS} 个）"
    points = round(100 * (week["coverage_share"] - prior["coverage_share"]))
    return f"{points:+d} 个百分点"


def coverage_lines(coverage: dict[str, Any]) -> list[str]:
    """One screen of the daily report: facts and trends only, no study advice."""
    periods = coverage["periods"]
    lines = [
        "能过 50% 必备门槛的职位占比，只算 AI 拆解过的职位：",
        "",
        f"- 今天：{_share(periods['today'])}",
        f"- 近 30 天：{_share(periods['last_30_days'])}",
        f"- 比上周：{_change(periods['last_7_days'], periods['prior_7_days'])}",
    ]
    if coverage["archetypes"]:
        parts = [
            f"{ARCHETYPE_LABEL.get(row['archetype'], row['archetype'])} "
            f"{row['coverage_share']:.0%}（{row['jobs_scored']} 个）"
            for row in coverage["archetypes"]
        ]
        lines.append(f"- 按岗位类型：{'，'.join(parts)}")
    if coverage["top_skills"]:
        total = coverage["top_skills"][0]["jobs_30d"]
        lines += [
            "",
            f"近 30 天最常要求的必备技能（共 {total} 个职位）：",
            "",
            "| 技能 | 要求它的职位 | 档案状态 | 趋势 |",
            "| --- | ---: | --- | --- |",
        ]
        lines += [
            f"| {row['skill_name']} | {row['must_have_share']:.0%}（{row['must_have_jobs']}） "
            f"| {STATUS_LABEL[row['status']]} | {TREND_LABEL[row['trend']]} |"
            for row in coverage["top_skills"]
        ]
    return lines
