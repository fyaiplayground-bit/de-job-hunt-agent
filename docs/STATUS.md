# Status

**Last updated:** 2026-10-30 · **Phase:** Milestone 1 (skeleton + ingestion)

Update this file at the end of every work session: what got done, what's next, what's blocked.

## Where we are

- Design confirmed (see `docs/DESIGN.md`, `docs/DECISIONS.md`).
- Starter kit created: `CLAUDE.md`, docs, 6 skill files, `.gitignore`, `.env.example`, `private/README.md`.
- Repo is on GitHub (public): https://github.com/fyaiplayground-bit/de-job-hunt-agent. No code yet.
- FL's real resume and Evidence Bank come last (Milestone 5). Until then everything is built and tested against the fake sample profile in `data/sample/` (decision #16).

## Waiting on FL

- [x] Put the starter kit in a folder named `de-job-hunt-agent` and open it in Claude Code
- [x] GitHub account + empty **public** repo named `de-job-hunt-agent` (no README, no .gitignore — we have our own)
- [x] Install Docker Desktop
- [ ] Anthropic API key from the Claude Console, with a monthly spending limit → put it in `.env` (never in chat, never committed) — needed by Milestone 2
- [ ] Personal AWS account + S3 bucket for backups (not the work account) — needed by Milestone 4
- [ ] Open questions (can wait until Milestone 5): target archetype(s); location / remote, comp floor, work-authorization answers; companies to exclude; daily application target

## Milestones

### Milestone 1 · Week 1 · Skeleton + ingestion
- [x] git init, first commit, push to GitHub
- [x] `docker-compose.yml` with Postgres; confirm it starts
- [x] Python project setup (dependencies, ruff, pytest)
- [x] JD safety gate (adapted from ai-job-search)
- [x] Ingestion: Greenhouse + Lever for a starter list of companies → raw tables (19 boards; the small-company target list comes in M5)
- [ ] Ingestion: freehire.me; LinkedIn public listings behind a flag (default off)
- [ ] Idempotent load + dedupe (including the same job arriving from freehire and Greenhouse/Lever); daily run script — idempotent load done (#21); cross-source dedupe and daily script still to do
- [x] Alarm triage + rules loop step A: deterministic tiers, `config/triage_rules.toml`, golden set, `pipeline.alarm_report` (#22)
- [ ] Rules loop step B: labels table, labeling command, `evaluate_rules` comparing proposed vs current rules; walk the loop once end to end (#22)
- [ ] Fake sample profile in `data/sample/`: a made-up DE-transition candidate (resume, Evidence Bank, Applicant Profile) in exactly the formats the real ones will use

### Milestone 2 · Week 2 · Agents
- [ ] Agent modules loading rules from `.claude/skills/`
- [ ] Choose resume template engine (LaTeX vs Typst); one-page template
- [ ] Tailor → reviewer → revise loop; PDF compile-and-inspect; ATS text-layer check
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

Claude: build rules loop step B (labels table + labeling command + `evaluate_rules`; show the short design first), then propose the freehire.me + LinkedIn public ingestion design.

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
