---
name: fit-scoring
description: Score how well FL fits a job (0–100) against her Evidence Bank and decide Apply + referral / Apply / Skip / Big-tech later. Use after jd-analysis, before any tailoring work.
---

# Fit Scoring (Agent 2)

Decide whether a job is worth an application. Lean toward applying: postings are wish lists and FL is learning fast.

## Inputs

- The JD brief from `jd-analysis`
- `private/evidence_bank.md` (the only source of facts about FL)
- `private/applicant_profile.md` and `private/target_companies.md` (dealbreakers, exclusions, target lists)

## How a skill counts

A skill counts if FL has used it at all — at work, in a project (in-progress projects like GH Archive included), or in practice work. Record *how* she used it, for interview prep, never to filter:

- `production` — used at work on real systems
- `project` — built with it in a personal project
- `practiced` — exercises, courses, small experiments

A skill with no Evidence Bank entry at all is `not_covered`.

## Scoring

1. Must-have coverage = covered must-haves ÷ all must-haves (core keywords count double).
2. Nice-to-have coverage adds up to 10 points.
3. Archetype fit: analytics engineer +5, pipeline DE 0, infra DE −5 (adjust as FL's skills grow).
4. Score = 80 × must-have coverage + nice-to-have points + archetype adjustment, capped at 100.

## Decision

| Condition | Decision |
| --- | --- |
| Dealbreaker hit (location, remote policy, comp floor, sponsorship, excluded company) | **Skip** — name the dealbreaker |
| Big-tech company and FL hasn't switched to the big-tech phase | **Big-tech later** — keep on the target list |
| Must-have coverage ≥ ~50% and score ≥ 65 | **Apply + referral** (find contacts) |
| Must-have coverage ≥ ~50% | **Apply** |
| Below ~50% | **Skip** — list the missing must-haves |

## BIE → DE angle

Always name which of FL's BI work is genuinely DE work for this job (pipelines, Redshift/Glue/Athena, data modeling, SQL at scale, orchestration) so the tailor leads with it.

## Output

```
{"score": 0, "decision": "", "must_have_coverage": 0.0,
 "covered": [{"skill": "", "level": "production|project|practiced", "evidence": ""}],
 "not_covered": [], "dealbreakers": [], "lead_with": []}
```
