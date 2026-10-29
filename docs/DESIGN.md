# Design

Condensed from the full design doc in the claude.ai "Job Hunting" Project ("DE Job Hunt Agent System — Design"). If the two disagree, this repo copy wins; record the change in `DECISIONS.md`.

## Goal

Land Data Engineer interviews: small companies first for interview practice, big tech as the final target. Send fewer, sharper applications (tailored resume + a warm contact) rather than spray-and-pray, while FL spends her time studying.

## What stays human

- Final submit (FL approves each batch in chat)
- Passwords, account creation, CAPTCHAs
- Anything sent from FL's LinkedIn (agents draft, FL sends)

## Data flow

```
Sources (Greenhouse, Lever, freehire, LinkedIn public)
   │  ingestion/  (daily)
   ▼
raw.job_postings          ← JSON as fetched, never modified; backed up to S3
   │  JD safety gate + dedupe
   ▼
staging (dbt)             ← cleaned text, company, location, dates
   ▼
skills (dbt + Agent 1)    ← extracted must-haves / nice-to-haves / keywords per JD
   ▼
marts (dbt)               ← fit scores, skill frequency, coverage, application funnel
   │
   ├─► Agents 2–7 per job ──► tailored PDF + outreach drafts + approval queue
   ├─► Agent 9 daily ───────► coverage report
   └─► Streamlit dashboard
```

Facts about FL come only from `private/evidence_bank.md` and `private/applicant_profile.md`.

## Agents

| # | Agent | Job | Skill file |
| --- | --- | --- | --- |
| 1 | JD Analyst | Must-haves vs nice-to-haves, exact keywords, archetype, hidden signals, seniority | `jd-analysis` |
| 2 | Fit Scorer | Score 0–100 → Apply + referral / Apply / Skip / Big-tech later; ~50% bar | `fit-scoring` |
| 3 | Researcher | Company stack, news, likely team members, talking points (public info only) | (inside `outreach-drafting`) |
| 4 | Resume Tailor | One-page PDF in the JD's words, F-pattern layout, drafter → reviewer → revise | `resume-tailoring` |
| 5 | Critic | Parse check, keyword coverage, evidence check, 7-second test, layout, hygiene | `ats-critic` |
| 6 | Submitter | Claude in Chrome from the claude.ai Project; fill to review page; FL approves | (not in repo) |
| 7 | Networker | 2–3 people per job + draft notes; recruiter reply drafts | `outreach-drafting` |
| 8 | Tracker | Stage per job, follow-up dates, weekly funnel, interview prep pack | (dbt marts + Project) |
| 9 | Coverage Reporter | Do have + learning skills cover most target jobs? | `coverage-report` |

## Tracker stages

Found → Scored → Tailored → Awaiting approval → Applied → Recruiter screen → Tech screen → Onsite → Offer / Rejected / Ghosted

## Expertise baked in (summary)

- **ATS reality:** parsers store fields, recruiters search by keyword and knockout questions. Single column, standard headings, no tables/images/text boxes, nothing in headers/footers, consistent dates, text-based PDF.
- **Recruiter psychology:** ~7-second first scan in an F-pattern (Ladders eye-tracking, 2018). Top third decides; the first 2–3 words of each bullet carry the scan; numbers stop the eye; most relevant bullet first under each role; short bullets read as more credible.
- **Bullet formula:** action verb + what was built + tech/scale + measurable result.
- **BIE → DE framing:** keep the official title; signal direction in the headline; lead BI bullets with the engineering, dashboards as the outcome.
- **Outreach:** peer DE on the team first (they refer most), people who share FL's current or past employer next, hiring manager only with a specific note; small ask (15-minute chat) before a referral ask; 5–10 personal notes a day, all sent by FL.

## Full design doc

https://claude.ai/artifact/DCFpJPhEQohhgLPdZhHNRb
