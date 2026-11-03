---
name: fit-scoring
description: Score how well FL fits a job (0–100) against her Evidence Bank and decide Apply + referral / Apply / Skip. Use after jd-analysis, before any tailoring work. Runs as code (agents/fit_scoring.py), not as an LLM prompt.
version: 2
---

# Fit Scoring (Agent 2)

Decide whether a job is worth an application. Lean toward applying: postings are wish lists and FL is learning fast.

**This agent is code, not a prompt** (decision #35): `agents/fit_scoring.py` applies the rules below from `config/fit_scoring.toml` and `config/skill_vocabulary.toml`, so the same brief, profile and rules always give the same score. Change a number there, not here, through the rules loop. This file describes what the code does.

## Inputs

- The JD brief from `jd-analysis` (`agents.jd_briefs`)
- `<profile>/evidence_bank.toml` (the only source of facts about FL) and `<profile>/applicant_profile.toml` (dealbreakers)
- Later: `private/target_companies.md` (exclusions, big-tech list) for the big-tech phase

## How a skill counts

A skill counts if FL has used it at all — at work, in a project, or in practice work. The level is recorded for interview prep, never to filter:

- `production` — used at work on real systems
- `project` — built with it in a personal project
- `practiced` — exercises, courses, small experiments

A JD skill is covered when its name (or a part of it, e.g. "Cloud SQL / PostgreSQL") matches an Evidence Bank skill by name or alias, a synonym in the vocabulary ("ETL/ELT pipelines" → ETL), or a skill family ("AWS" is covered by Redshift, Glue, S3...). The posting's exact phrases may match by name, alias or synonym, but never through a family. No match means `not_covered`.

## Scoring

1. Must-have coverage = covered must-haves ÷ all must-haves, core skills counting double.
2. Nice-to-have coverage = covered ÷ listed; a posting with no nice-to-haves counts them as covered as well as its must-haves.
3. Score = 70 × must-have coverage + 20 × nice-to-have coverage + archetype adjustment (analytics engineer +5, pipeline DE 0, infra DE −5), kept within 0–100. Nice-to-haves weigh this much because meeting only the minimum can get a candidate screened out (FL, 2026-11-02); they rank jobs, they don't decide whether to apply.

## Decision

| Condition | Decision |
| --- | --- |
| Dealbreaker hit | **Skip** — name the dealbreaker |
| Must-have coverage below ~50% (decision #8) | **Skip** — list the missing must-haves |
| Score ≥ 65 | **Apply + referral** (find contacts) |
| Otherwise | **Apply** |

Dealbreakers:

- **Years:** the posting asks for more than FL's years + 1. Years count every data role (analyst and BIE alike). Seniority itself is not a dealbreaker (FL: senior roles are fine when she has the years).
- **Salary:** the posting's top of range is below the floor in the Applicant Profile.
- **Sponsorship:** the profile needs sponsorship and the posting won't sponsor.
- **Location:** off during the small-company practice phase (shown, never a reason to skip); the big-tech phase limits it to California, Washington and Texas.
- **No must-haves in the brief** (a cut-off posting): skip, nothing to judge.

## BIE → DE angle

`lead_with` lists the covered must-haves, core first and strongest level first, so the tailor leads with FL's BI work that is genuinely DE work for this job (pipelines, Redshift/Glue/Athena, data modeling, SQL at scale, orchestration).

## Output (stored in `agents.fit_scores`)

```
{"score": 0, "decision": "apply_referral|apply|skip",
 "must_have_coverage": 0.0, "nice_coverage": 0.0,
 "covered": [{"asked": "", "skill": "", "level": "production|project|practiced", "evidence": [], "via": "name|alias|synonym|family"}],
 "not_covered": [], "nice_covered": [], "nice_missing": [], "dealbreakers": [], "lead_with": [],
 "candidate_years": 0.0, "work_mode": "", "location": ""}
```
