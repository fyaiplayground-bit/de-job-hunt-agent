---
name: coverage-report
description: Daily report answering one question — do FL's current and in-progress skills cover most of the jobs she's targeting? Use for the scheduled morning run. Reports where she stands; does not recommend what to study.
---

# Skill Coverage Report (Agent 9)

## Inputs

- Every JD ingested in the last day and a rolling 30 days (from the `skills` / `marts` tables)
- `private/evidence_bank.md`, including skills marked `learning`

## Sections

1. **Coverage score** — share of target postings where FL's have + learning skills clear the ~50% apply bar. Show today, 30-day, and change versus last week. Split by segment: small companies vs big tech.
2. **Top 10 skills** — the most-requested skills across target DE postings:

   | Skill | Postings asking | FL status | Trend |
   | --- | --- | --- | --- |
   | e.g. SQL | 92% | have | → |

   Status is `have`, `learning` or `not covered`.
3. **Best-fit segments** — which archetypes (analytics engineer / pipeline DE / infra DE), company sizes and industries her current profile covers best, so the fit scorer leans toward them.
4. **Big-tech readiness** — coverage score on big-tech postings alone, so FL can see when the big-tech phase makes sense.

## Rules

- Report facts and trends only. No study recommendations.
- Keep it to one screen.
- Note the number of postings behind each figure.
