# Status

**Last updated:** 2026-10-28 · **Phase:** Milestone 1 (skeleton + ingestion)

Update this file at the end of every work session: what got done, what's next, what's blocked.

## Where we are

- Design confirmed (see `docs/DESIGN.md`, `docs/DECISIONS.md`).
- Starter kit created: `CLAUDE.md`, docs, 6 skill files, `.gitignore`, `.env.example`, `private/README.md`.
- Repo is on GitHub (public): https://github.com/fyaiplayground-bit/de-job-hunt-agent. No code yet.
- FL's real resume and Evidence Bank come last (Milestone 5). Until then everything is built and tested against the fake sample profile in `data/sample/` (decision #16).

## Waiting on FL

- [x] Put the starter kit in a folder named `de-job-hunt-agent` and open it in Claude Code
- [x] GitHub account + empty **public** repo named `de-job-hunt-agent` (no README, no .gitignore — we have our own)
- [ ] Install Docker Desktop
- [ ] Anthropic API key from the Claude Console, with a monthly spending limit → put it in `.env` (never in chat, never committed) — needed by Milestone 2
- [ ] Personal AWS account + S3 bucket for backups (not the work account) — needed by Milestone 4
- [ ] Open questions (can wait until Milestone 5): target archetype(s); location / remote, comp floor, work-authorization answers; companies to exclude; daily application target

## Milestones

### Milestone 1 · Week 1 · Skeleton + ingestion
- [x] git init, first commit, push to GitHub
- [ ] `docker-compose.yml` with Postgres; confirm it starts
- [ ] Python project setup (dependencies, ruff, pytest)
- [ ] JD safety gate (adapted from ai-job-search)
- [ ] Ingestion: Greenhouse + Lever for a starter list of small companies → raw tables
- [ ] Ingestion: freehire.me; LinkedIn public listings behind a flag (default off)
- [ ] Idempotent load + dedupe; daily run script
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

FL: install Docker Desktop. Then Claude writes `docker-compose.yml` with Postgres and confirms it starts.

## Session log

- 2026-10-27 — Design finalized in the claude.ai Project; starter kit written.
- 2026-10-28 — Decided to build the full system first on a fake sample profile; real resume plugged in at Milestone 5.
- 2026-10-28 — Unzipped starter kit into place; git init on `main`; removed FL's name and employer from public files (decision #17); first commit pushed to GitHub. `.gitignore` now also covers `*.zip` and `.claude/settings.local.json`.
