---
name: coverage-report
description: Daily report answering one question — do FL's current and in-progress skills cover most of the jobs she's targeting? Reports where she stands; does not recommend what to study. Runs as code on the dbt marts (agents/coverage_report.py), not as an LLM prompt.
version: 2
---

# Skill Coverage Report (Agent 9)

**This agent is code, not a prompt** (decision #41): `agents/coverage_report.py` reads the dbt marts and writes a section of the daily report; the Streamlit dashboard shows the same marts. This file describes what the code does.

## Inputs

- The jobs AI briefed and code scored, by the day they were first seen (`mart_coverage_summary`, `mart_coverage_by_archetype`, `mart_skill_frequency`)
- The profile's skills, including those marked `learning`, which count as covered (decision #13)

## Sections

1. **Coverage score** — share of scored postings where FL's have + learning skills clear the ~50% apply bar. Today, 30 days, and change versus last week.
2. **By role type** — analytics engineer, pipeline DE, infra DE, so the fit scorer's results can be read against them.
3. **Top 10 skills** — the most-requested must-have skills:

   | Skill | Postings asking | Profile status | Trend |
   | --- | --- | --- | --- |
   | e.g. SQL | 76% (66) | have | → |

   Status is `have`, `learning` or `not covered`.

Small companies vs big tech, company size and industry come in Milestone 5, with the target company list: the data for them doesn't exist yet.

## Rules

- Report facts and trends only. No study recommendations.
- Keep it to one screen.
- Note the number of postings behind each figure.
- A change from last week needs at least 20 scored postings in each week; below that it says there isn't enough data.
