---
name: resume-tailoring
description: Rewrite FL's resume for one job as a one-page, ATS-safe PDF using the JD's exact keywords, F-pattern layout and recruiter psychology, then run a drafter-reviewer loop. Use for every job scored Apply or Apply + referral.
---

# Resume Tailoring (Agent 4)

Write for two readers in order: a parser that reads every word literally, then a human who reads almost none of them.

## Inputs

- JD brief (`jd-analysis`), fit result (`fit-scoring`)
- `private/evidence_bank.md` — the only source of facts
- The resume template in `templates/`

## The keyword rule (advertise, don't invent)

| JD keyword | FL's situation | Action |
| --- | --- | --- |
| Something she did under another name | e.g., JD "data pipelines", resume "ETL jobs" | Rewrite in the JD's exact words |
| Something she touched (project, adjacent tool, light use) | Evidence Bank has an entry | Add it, framed as strongly as the experience allows |
| Something she never touched | No Evidence Bank entry | Leave it off; it appears as `not_covered` in the coverage report |

Never invent years of experience, titles, employers or metrics. Numbers come only from the Evidence Bank (rounded/sanitized for anything internal to FL's employer).

## Reader 1: the ATS

- Single column. Standard headings: Summary, Experience, Projects, Skills, Education.
- No tables, text boxes, icons, images, or important text in headers/footers.
- One date format (e.g., "Mar 2022 – Present").
- Place each core keyword twice: once in Skills, once inside a bullet with context.
- Include both forms where natural ("Apache Airflow", "ETL").
- Never hide keywords (white or tiny text) — the parsed text shows them to the recruiter.

## Reader 2: the recruiter (7-second F-pattern scan)

- **Top third decides.** Name, a headline naming the target role (e.g., "Data Engineer · SQL / Python / Spark"), a 2-line summary.
- **Left edge carries the scan.** Start every bullet with a strong verb + the DE noun ("Built ingestion pipeline…", "Migrated 40 tables…"), never "Responsible for…".
- **Numbers stop the eye.** Aim for numbers in at least half the bullets: data volume, runtime/latency cut, cost saved, SLA, sources/pipelines owned, data-quality incidents reduced.
- **Order bullets by relevance to this job**, most relevant first under each role.
- **Titles, companies, dates aligned on the left**; make a well-known current employer impossible to miss.
- Short bullets (1–2 lines), consistent tense, white space between sections. One page.

## BIE → DE framing

- Keep the official title (background checks verify it); signal the direction in the headline and summary.
- Lead BI bullets with the engineering (ingestion, modeling, orchestration, performance); the dashboard is the outcome.
- A Projects section carries DE work outside the day job (GH Archive, this repo).

## Bullet formula

Action verb + what was built + tech/scale + measurable result.
Shape: "Built a daily Glue + Redshift pipeline ingesting N sources, cutting report latency from X hours to Y minutes."

## Process (drafter → reviewer → revise)

1. Draft the tailored content.
2. A reviewer with fresh context (no access to the drafter's reasoning) researches the company and critiques: missed keywords, weak framing, generic language.
3. Revise.
4. Compile to PDF; inspect the rendered page; fix layout until it is exactly one clean page.
5. Hand to `ats-critic`.

## Outputs per job (in `private/output/<company>_<role>/`)

1. `FirstLast_DataEngineer_<Company>.pdf`
2. `changes.md` — every edit and the JD requirement it serves
3. `not_covered.md` — JD asks with no Evidence Bank entry
4. Cover note only if the application asks for one
