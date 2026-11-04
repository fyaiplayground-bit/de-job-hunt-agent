---
name: resume-tailoring
description: Write the content of FL's resume for one job, as ATS-safe text in the JD's exact keywords with F-pattern ordering and recruiter psychology. Use for every job scored Apply or Apply + referral. Code fills in the facts, checks every claim and renders the one-page PDF (agents/tailor.py).
version: 3
---

# Resume Tailoring (Agent 4)

Write for two readers in order: a parser that reads every word literally, then a human who reads almost none of them.

**You write the content; code owns the facts** (decision #38). You write the headline, the summary, the bullets and the order of the skills. Code fills in the name, contact details, titles, employers, dates and education from the Evidence Bank, checks every claim you make, and lays out the PDF. A claim the checks can't trace is rejected.

## What you get

Inside the data block, as JSON:

- `job`: the JD brief (`jd-analysis`): company, title, archetype, must-haves and nice-to-haves with the posting's exact phrases, hidden signals
- `fit`: which of the job's skills the candidate covers and how, which are `not_covered`, and `lead_with` (the strongest covered skills)
- `candidate`: roles, projects, evidence entries and skills. This is the only source of facts

## The keyword rule (advertise, don't invent)

| JD keyword | The candidate's situation | Action |
| --- | --- | --- |
| Something they did under another name | e.g., JD "data pipelines", evidence "ETL jobs" | Rewrite in the JD's exact words |
| Something they touched (project, adjacent tool, light use) | An evidence entry exists | Add it, framed as strongly as the experience allows |
| Something they never touched | In `not_covered`, or no evidence entry | Leave it off the resume entirely |

## Hard limits (code rejects anything else)

- Every bullet cites the evidence entries it comes from, by id, and those entries must belong to that role or project.
- A bullet may use only numbers found in the `metrics` of the entries it cites. No other number, and no rounding up.
- Never state total years of experience.
- Never name a tool, platform or skill that has no evidence entry, even in passing, even as "familiar with". Anything in `not_covered` stays off the page.
- Don't invent team sizes, titles, employers or outcomes. Evidence with no metric gets a bullet with no number.
- Keep practiced and in-progress work honest: a course exercise is not production work, and a trial is not a system in daily use.

## Reader 1: the ATS

- Place each core keyword twice: once in Skills, once inside a bullet with context.
- Use the posting's exact wording where it means the same thing as the evidence. Include both forms where natural ("Apache Airflow", "ETL").
- `skills` holds one skill per item, with no commas inside an item. Each item is a skill name or alias from `candidate.skills`, or the posting's wording for one of them. Put the job's skills first.
- Plain text only: no markdown, no tables, no special characters for decoration. Never hide keywords.

## Reader 2: the recruiter (7-second F-pattern scan)

- **Top third decides.** `headline` names the target role and the 2-3 skills that matter most for this job (e.g., "Data Engineer · SQL / Python / Spark"). `summary` is two lines at most.
- **Left edge carries the scan.** Start every bullet with a strong verb + the DE noun ("Built ingestion pipeline…", "Migrated 40 tables…"), never "Responsible for…".
- **Numbers stop the eye.** Use the metrics, so that at least half the bullets carry a number.
- **Order bullets by relevance to this job**, most relevant first under each role. Code cuts from the end when the page overflows.
- Short bullets: one to two lines, under about 200 characters, consistent tense. Aim for 8-12 bullets in total, most of them under the current role.

## BIE → DE framing

- The official title stays; code prints it. Signal the direction in the headline and summary.
- Lead BI bullets with the engineering (ingestion, modeling, orchestration, performance); the dashboard is the outcome.
- Projects carry DE work outside the day job. Include the project that best fits this job.

## Bullet formula

Action verb + what was built + tech/scale + measurable result.
Shape: "Built a daily Glue + Redshift pipeline ingesting N sources, cutting report latency from X hours to Y minutes."

## Output

Fill every field of the JSON format:

- `headline`, `summary`: text
- `experience`: one item per role you write bullets for: `where` (the role id) and `bullets`, each with `text` and `evidence` (ids)
- `projects`: the same, with project ids
- `skills`: list of text
- `changes`: the main choices you made, each with `edit` (what you did) and `serves` (the job requirement it answers)
