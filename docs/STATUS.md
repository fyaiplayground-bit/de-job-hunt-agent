# Status

**Last updated:** 2026-11-03 · **Phase:** Milestone 2 (agents) in progress; 2.4 done, 2.5 (tailoring) next

Update this file at the end of every work session: what got done, what's next, what's blocked.

## Where we are

- Design confirmed (see `docs/DESIGN.md`, `docs/DECISIONS.md`).
- Repo is on GitHub (public): https://github.com/fyaiplayground-bit/de-job-hunt-agent.
- **Milestone 1 complete (2026-10-31):** daily ingestion from Greenhouse, Lever and freehire into Postgres (raw, idempotent), safety gate with deterministic triage and the rules loop, cross-source dedupe, scheduled daily run with report. M1 interview note in `docs/INTERVIEW_NOTES.md`.
- FL's real resume and Evidence Bank come last (Milestone 5). Until then everything is built and tested against the fictional sample profile in `data/sample/` (decisions #16, #28); `PROFILE_DIR` switches it to `private/`.

## Waiting on FL

- [x] Put the starter kit in a folder named `de-job-hunt-agent` and open it in Claude Code
- [x] GitHub account + empty **public** repo named `de-job-hunt-agent` (no README, no .gitignore — we have our own)
- [x] Install Docker Desktop
- [x] Anthropic API key from the Claude Console (own workspace + monthly spending limit) in `.env`; first live `agents.llm ping` ok 2026-11-01. Key expires **2027-04-30**: remind FL to rotate around 2027-04-15 (new key in the same workspace, replace the line in `.env`, Claude runs `agents.llm ping`)
- [ ] Personal AWS account + S3 bucket for backups (not the work account) — needed by Milestone 4
- [ ] Open questions (can wait until Milestone 5): target archetype(s); location / remote, comp floor, work-authorization answers; companies to exclude; daily application target

## Milestones

### Milestone 1 · Week 1 · Skeleton + ingestion
- [x] git init, first commit, push to GitHub
- [x] `docker-compose.yml` with Postgres; confirm it starts
- [x] Python project setup (dependencies, ruff, pytest)
- [x] JD safety gate (adapted from ai-job-search)
- [x] Ingestion: Greenhouse + Lever for a starter list of companies → raw tables (19 boards; the small-company target list comes in M5)
- [x] Ingestion: freehire.me; LinkedIn public listings behind a flag (default off) — LinkedIn built and tested, no live request yet (#24)
- [x] Idempotent load + dedupe (including the same job arriving from freehire and Greenhouse/Lever); daily run script — #21, #24, #27; scheduled daily (9:30 LA since #29), desktop shortcut to the report
- [x] Alarm triage + rules loop step A: deterministic tiers, `config/triage_rules.toml`, golden set, `pipeline.alarm_report` (#22)
- [x] Rules loop step B: labels table, labeling command, `evaluate_rules` comparing proposed vs current rules; walked once end to end (#23)
- [x] Fake sample profile in `data/sample/`: a made-up DE-transition candidate (resume, Evidence Bank, Applicant Profile) in exactly the formats the real ones will use — TOML + resume.md, checked by `agents.profile check` (#28)
- [x] M1 interview note in `docs/INTERVIEW_NOTES.md`

### Milestone 2 · Week 2 · Agents
- [x] Agent modules loading rules from `.claude/skills/` — 2.1: skill loader + prompt lock, LLM client with cache (#30)
- [x] Resume template: Typst (#30), one-page template with bundled fonts (2.4, #36)
- [x] jd-analysis (2.2: brief schema, golden set + evaluation, prompt v3, daily briefs of new jobs; #31–#33)
- [x] fit-scoring as code (2.3: vocabulary matching, 70/20 score, dealbreakers, daily "worth applying"; #35) and coverage checks (#34)
- [x] PDF compile-and-inspect; ATS text-layer check (2.4, `agents/pdf_checks.py`, `agents.render_resume`; #36)
- [ ] Tailor → reviewer → revise loop
- [ ] Approval queue output for the claude.ai Project to submit from
- [ ] End-to-end test: real JDs from the pipeline + the sample profile → tailored PDFs

### Milestone 3 · Week 3 · Modeling + reporting
- [ ] dbt models: staging → skills → marts
- [ ] Daily coverage report (Agent 9)
- [ ] Streamlit dashboard (skill trends, application funnel)

### Milestone 4 · Week 4 · Production polish
- [ ] Airflow DAGs calling the pipeline functions
- [ ] FastAPI endpoints: /analyze, /score, /tailor, /critique, /coverage
- [ ] Nightly S3 backup
- [ ] README with architecture diagram; interview notes

### Milestone 5 · Go live with FL's real profile
- [ ] FL provides her resume + summaries of GH Archive, Python Practice, Data Engineer career
- [ ] Build the real Evidence Bank and Applicant Profile in `private/` (same format as the sample)
- [ ] Answer the open questions; fill `private/target_companies.md`
- [ ] Point the config from `data/sample/` to `private/`; review the first real tailored resumes
- [ ] Start the daily submit queue (small companies first)

## Next action

**Waiting on FL (from the first full run, 11/03):**
1. **Daily cap:** 70 new jobs were in scope, the cap of 50 left 20 unbriefed, and those are not retried (the run only reads that day's new postings). The cap picks by newest posting id, not by quality. FL decides whether to raise `JD_ANALYSIS_DAILY_MAX` (about $0.04 a job; at 50 a day about $60 a month) or keep it.
2. **Alarms:** 7 unlabeled review alarms (the earlier "11" counted labeled ones too): `pipeline.alarm_report`, `pipeline.labels add`. None reach the LLM.

**FL any time:** send jobs found on LinkedIn (company + title); Claude runs `pipeline.find_job` and reports; `--stats` gives coverage.

**Claude, after a few more days of briefs:** run `agents.fit_scoring unmatched` and grow `config/skill_vocabulary.toml` through the loop.

**Next build step: 2.5,** the tailor → reviewer → revise loop (design first, wait for FL's OK). The drafter writes the `resume.md` format, so `check_resume` and `agents.render_resume` already cover its output (#36); `check_pdf(required=...)` takes the JD keywords. The fictional sample fills 67% of the page, which gives a thin-page warning; that is content, not a template fault.

Standing facts: the clearance rule is on (fit-scoring rules v2, #37); FL fills in `has_security_clearance` and `can_obtain_security_clearance` at Milestone 5 (the sample has both false). Fit scoring's location check is OFF during the small-company practice phase (final targets California, Washington, Texas for the big-tech phase). The daily run happens by itself at 9:30 LA (#29) and catches up about 6 minutes after the laptop wakes; check it at session start.

## Session log

- 2026-10-27 — Design finalized in the claude.ai Project; starter kit written.
- 2026-10-28 — Decided to build the full system first on a fake sample profile; real resume plugged in at Milestone 5.
- 2026-10-28 — Unzipped starter kit into place; git init on `main`; removed FL's name and employer from public files (decision #17); first commit pushed to GitHub. `.gitignore` now also covers `*.zip` and `.claude/settings.local.json`.
- 2026-10-28 — Cloned ai-job-search into `reference/` (gitignored, commit `83c788d`); added the "Borrowed from ai-job-search" table to DESIGN.md, the MIT header rule to CLAUDE.md, `LICENSES/ai-job-search-MIT.txt`, decision #18.
- 2026-10-28 — Docker Desktop installed (per-user, WSL 2). Added `docker-compose.yml`: Postgres 17, values from `.env`, port bound to 127.0.0.1, `pgdata` volume, health check. Verified: healthy, password login works, a test row survived `down` + `up`. `.env` created locally with a generated DB password (not committed).
- 2026-10-28 — Added `docs/JOURNAL.md` (step log with commits and undo) and `docs/NOTES.md` (study notes by topic); CLAUDE.md now says which doc holds what and to write the journal entry in the same commit as each step.
- 2026-10-30 — Python project set up with uv: Python 3.12.16, httpx / psycopg / python-dotenv, pytest + ruff, `pipeline/config.py`, smoke tests (4 pass with the DB up; DB test skips when it is down). Decision #19.
- 2026-10-30 — JD safety gate: copied the detection logic into `pipeline/posting_guard.py` (identical to upstream, 389 lines), our wrapper `pipeline/safety_gate.py`, their 59 tests ported plus 13 of ours; smoke tests split into unit (`test_config.py`) and smoke (`test_db_smoke.py`). Decision #20.
- 2026-10-30 — Greenhouse + Lever ingestion: 4 raw/gate tables via migrations, 19 boards, 2300 postings loaded; second same-day run added 0 (idempotent). Gate: 14 alarms, all false positives (10 "You are an AI pragmatist", 3 SSH in skill lists, 1 "as an AI/Tech evangelist"), 0 among 58 DE-type titles. DB host default → 127.0.0.1 (tests 69s → 2s). Decision #21.
- 2026-10-30 — Deterministic alarm triage (clean/benign/review/block) with rules in `config/triage_rules.toml` and a 39-case golden set; gate version now `d1-t1`, all 2300 postings recomputed from raw (clean 2286, benign 14, review 0, block 0), old results kept. Principle "code decides, AI proposes, rules change only through the loop" added to CLAUDE.md. Decision #22.
- 2026-10-30 — Rules loop step B: `gate.labels`, `pipeline.labels` (add/list/export), `pipeline.evaluate_rules`, `config/proposals/`. Walked the loop on real data: 14 false positives labeled → 5 golden cases; two weakening proposals rejected (one showed 0 changed postings and was caught only by the golden set), comment-only proposal passed. Rules stay v1. 191 tests pass. Decision #23.
- 2026-10-31 — freehire ingestion (7-day backfill, capped at 5000), LinkedIn built but off, exact cross-source dedupe views (7118 → 7073 jobs), `discover_boards`. Fixed a dedupe view that stalled at 7k rows (migration 007, 0.59 s). 211 tests pass. 9 new alarms await FL. Decision #24.
- 2026-10-31 — First real turn of the rules loop: 9 freehire alarms labeled false positive (13 golden cases), triage rules v2 adopted (zero-width editing artifacts no longer block; evaluation PASS, only the 5 labeled postings moved), recomputed 7,118 postings → block 0. HTTP identity per #25 (conventional crawler UA, Accept headers, jitter, LinkedIn 404 skip; no site-imitating header). 233 tests pass. Decisions #25, #26.
- 2026-10-31 — Daily run `pipeline.daily`: Docker auto-start, advisory lock, adaptive search window (2–7 days), report in `output/daily/` + `ops.daily_runs`; "new" by run ids. Two real runs ok, lock verified. CLAUDE.md: summarize the last daily run at session start. 244 tests pass. Decision #27.
- 2026-10-31 — Created the Windows scheduled task (8:30 LA, catch-up, on battery, headless) and the desktop shortcut "每日职位报告" with FL's OK; a manual trigger succeeded (result 0). Fixed a trigger saved with a fixed DST offset (would have run at 7:30 after Nov 1).
- 2026-10-31 — Fictional sample profile (Alex Sample, BI engineer → DE) in `data/sample/`: `evidence_bank.toml`, `applicant_profile.toml`, `resume.md`; `agents/profile.py` loads and checks them (resume traces to the Evidence Bank); `PROFILE_DIR` setting; private/README and skill files point at the profile folder; M1 interview note written. **Milestone 1 complete.** 269 tests pass. Decision #28.
- 2026-11-01 — First scheduled run (8:30) missed: laptop asleep 9:21 p.m.–9:03 a.m. Ran it manually (run 4: ok, 163 new, 30 DE, no alarms). Schedule moved to 9:30 with FL's OK (#29). Whether the catch-up fires stays unverified (see JOURNAL 1.12).
- 2026-11-01 — M2 design approved (#30: LLM reads and drafts, code scores and decides; Typst; Opus 5.5 at medium effort). Step 2.1: Anthropic SDK, `agents/skills.py` + `config/prompt_lock.toml` (prompt text can't change without a version bump), `agents/llm.py` (request builder, posting as data, structured output, fallback, `agents.llm_calls` cache with cost), `ping` and `costs` commands, migration 009. 297 tests pass. No live call yet: API key not set.
- 2026-11-01 — Step 2.2a: `config/analysis_scope.toml` (code pre-filter: 879 DE-titled → 442 in scope), strict brief schema, `jd-analysis` prompt v2, `agents.jd_briefs` (migration 010), `agents.jd_analysis run/show`. Live pilot: 20 briefs, $0.76, no declines. 308 tests pass. Decision #31.
- 2026-11-01 — Step 2.2b (part 1): golden set of 10 real postings (ids + expected values only), `agents.evaluate_prompt`, proposals jd-analysis v3 (years = overall requirement) and analysis scope v2 (skip snippets under 1,000 chars); board location moved out of the LLM input. Live eval: v3 years 10/10 (v2 7/10), must-haves 73/75 (v2 72/75), PASS; v3 at low effort equally good, $0.033 vs $0.038 a posting. Waiting for FL to review labels and approve. 317 tests pass.
- 2026-11-02 — 9:30 run missed (laptop asleep 9:18–19:33); the scheduled task caught up by itself at 19:39, 6 minutes after waking: catch-up verified (JOURNAL 1.13). Run 5 ok: 532 new jobs, 76 DE, 1 new alarm (CDW "AI forward company", likely false positive, FL to label). Local review page for the golden labels (`output/golden_review.html`, not committed) so FL can read each posting next to its labels.
- 2026-11-02 — FL reviewed the golden labels on the review page; nice-to-haves added to the golden set and checked by the evaluation (`--review` page built in). Adopted jd-analysis v3 (years = overall requirement), analysis scope v2 (skip snippets under 1,000 chars), effort stays medium. Decision #32. 425 postings in scope under v3. 320 tests pass.
- 2026-11-02 — Step 2.2c: the daily run now briefs that day's new in-scope jobs (cap `JD_ANALYSIS_DAILY_MAX` 50, switch `JD_ANALYSIS_ENABLED`), with an AI section in the report; an AI failure never costs the day's ingest; no backfill of the 425 existing postings (FL: test the whole flow first). Decision #33. Real runs 6 (partial: freehire read timeout) and 7 (ok) had no new in-scope jobs, so 0 briefed; first real use 11/03. 327 tests pass.
- 2026-11-02 — Labeled the CDW alarm a false positive (14 golden cases). Coverage checks: `pipeline.find_job` finds a job FL saw elsewhere or explains the miss with one live freehire check, logged in `ops.coverage_checks` (migration 011), `--stats` = measured recall. Trial: Netflix AE roles missed because they predate our first freehire backfill. FL answered the 2.3 questions (see Next action). Decision #34. 341 tests pass.
- 2026-11-02 — Fixed a silent data-loss bug in freehire paging (a short page mid-results was taken as the end; now paging follows `meta.total`). 30-day freehire backfill (FL approved, no AI): +4,939 postings, 15,434 jobs total; Netflix 10/20 AE role now found. Remaining gap: ~1,300 "data engineer" results beyond the API's 10,000 window only partly recovered via work-mode splits (daily 2-day runs are far below the window). 11 unlabeled review alarms wait for FL. 342 tests pass.
- 2026-11-02 — Step 2.3: fit-scoring as code (`agents/fit_scoring.py`, `config/fit_scoring.toml`, `config/skill_vocabulary.toml`, `agents.fit_scores` migration 012); the daily run scores the day's briefs and the report lists "今天值得投的". Trial on the 20 v2 pilot briefs: skip 11, apply 8, referral 1; a phrase-through-family false match (Snowflake) found and fixed. Decision #35. 361 tests pass.
- 2026-11-03 — 9:30 run missed again (laptop asleep until 19:03), catch-up started 19:09. Run 8 ok, the first full end-to-end test: 741 new jobs, 155 DE, 70 in scope, 50 briefed under `jd-analysis@3` for $2.08 (20 over the cap), 50 scored (22 worth applying, 28 skipped), 1 new review alarm, no failed sources; both new report sections present. Found: nothing checks security clearance, so a TS/SCI job ranked first.
- 2026-11-03 — Step 2.4: Typst one-page template with bundled Liberation Sans, `agents/resume_doc.py`, `agents/pdf_checks.py` (part copied from ai-job-search under MIT), `agents.render_resume` with a review page. Dates now use an ASCII hyphen; `resume-tailoring` v2. Sample renders to 1 page, all checks pass, byte-identical on re-render. Decision #36. 392 tests pass.
- 2026-11-03 — Clearance dealbreaker written as proposal `fit_scoring.v2` with `agents.evaluate_fit_rules` and 44 golden cases; two new Applicant Profile fields. Not adopted yet: waiting for FL's OK on the review page. 452 tests pass.
- 2026-11-03 — FL approved; clearance rule adopted as fit-scoring rules v2 (#37), skill v3, rescored: apply 20, skip 30, both Maxar TS/SCI jobs now skip. 452 tests pass.
