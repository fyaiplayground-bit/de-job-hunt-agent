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

## Determinism and the rules loop

Code decides at runtime; AI only proposes (DECISIONS #22). Every pipeline judgment is code plus a versioned rules or prompt file, checked by a golden set of labeled cases, and changed only through this loop:

```
daily run ──► results stored with the rules version
   │
report (pipeline.alarm_report) ──► FL labels: false positive / attack / unsure
   │
labels ──► golden set (tests/fixtures/*.jsonl)
   │
agent proposes a rules change ──► evaluate: every labeled case + every stored posting
   │                               (no known attack may become benign)
FL approves ──► bump version ──► recompute from raw ──► DECISIONS entry
```

First use: gate triage (`clean` / `benign` / `review` / `block`), rules in `config/triage_rules.toml`. Commands for each step: `pipeline.alarm_report` (report), `pipeline.labels add | export` (labels → `tests/fixtures/gate_cases_labeled.jsonl`), proposals in `config/proposals/`, `pipeline.evaluate_rules` (evaluate), `pipeline.ingest --gate-only` (recompute). In M2 the same applies to LLM steps: outputs cached by (input hash, prompt version, model), prompt changes evaluated against golden sets.

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

## Borrowed from ai-job-search

Source: [ai-job-search](https://github.com/ai-job-search-dev/ai-job-search), MIT, read at commit `83c788d` (2026-10-27). A read-only clone lives in `reference/ai-job-search/` (gitignored); never import from it. See DECISIONS #12 and #18.

| Piece | Their file(s) | Our target | How | Milestone |
| --- | --- | --- | --- | --- |
| JD safety gate | `tools/posting_guard.py` (+ its tests) | `pipeline/posting_guard.py` (copy), `pipeline/safety_gate.py` (our wrapper), `tests/test_posting_guard.py` | **Copy**: detection logic unchanged (checked line by line); CLI and file reading dropped; `run_gate()` returns a `GateResult` with a gate version. Their `tools/page_decode.py` charset fallback is **idea only** (our sources return UTF-8 JSON) | M1 (done) |
| PDF text-layer check | `tools/verify_pdf.py` | `agents/pdf_checks.py` | **Copy**: page count, keyword presence, ASCII date ranges (pypdf) | M2 |
| PDF layout check | `tools/verify_layout.py` | `agents/pdf_checks.py` | **Idea**: measure layout instead of eyeballing it. Theirs targets moderncv/LaTeX and needs Poppler; rebuild in pure Python once the template engine is chosen | M2 |
| LinkedIn public listings | `.agents/skills/linkedin-search/` (TypeScript/bun) | `ingestion/linkedin.py` | **Port to Python**: same logged-out guest endpoints, card/detail parsing, retry with backoff, honest User-Agent; off by default | M1 |
| freehire.me | `.agents/skills/freehire-search/` (TypeScript/bun) | `ingestion/freehire.py` | **Port to Python**: API client, retry with backoff. freehire aggregates ~50 ATSs, so dedupe must catch the same job arriving from freehire and Greenhouse/Lever | M1 |
| Drafter → reviewer → revise | `.claude/commands/apply.md`, `.claude/agents/application-reviewer.md` | `agents/tailor.py`, `agents/reviewer.py` | **Idea**: reviewer in a fresh context returns exact old → new edits, drafter applies them, then compile-and-inspect until clean. No cover letter; grounding follows DECISIONS #9, not their stricter audit | M2 |
| Interview prep | `.claude/skills/job-application-assistant/07-interview-prep.md` | `.claude/skills/interview-prep/SKILL.md` (new) | **Idea**: STAR stories, tough questions, questions to ask; rewritten for DE interviews (SQL, pipeline design, modeling) | M5 |
| Outcome tracking | `.claude/commands/outcome.md` | applications table in Postgres + dbt funnel mart | **Idea**: fixed status vocabulary, follow-up after N quiet days, stale sweep to Ghosted, outcomes feed back into fit scoring | M3 |

**License rule:** any file that copies or ports their code (Copy and Port rows) starts with this header, and the full MIT text is kept in `LICENSES/ai-job-search-MIT.txt`:

```python
# Adapted from ai-job-search (https://github.com/ai-job-search-dev/ai-job-search),
# <their file> at commit <hash>.
# Copyright (c) 2026 Mads Lorentzen. MIT License; full text in LICENSES/ai-job-search-MIT.txt
```

Idea rows need no header; the README credit covers them.

## Full design doc

https://claude.ai/artifact/DCFpJPhEQohhgLPdZhHNRb
