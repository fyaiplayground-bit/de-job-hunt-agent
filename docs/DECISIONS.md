# Decisions log

Newest at the bottom. Never delete an entry; if a decision changes, add a new entry and mark the old one **Superseded by #N**.

Format: number · date · decision · why · alternatives considered.

---

### #1 · 2026-10-27 · Two working surfaces
- **Decision:** Build the repo in Claude Code. Do daily job-hunt work (resume review, approving applications, recruiter replies) in the claude.ai Project "Job Hunting".
- **Why:** The repo needs persistent files, long-running services (Postgres, Airflow) and real subagents; daily work is conversation and judgment.
- **Alternatives:** Everything in claude.ai chat (no persistent workspace, no long-running processes).

### #2 · 2026-10-27 · Pipeline-centric, own repo
- **Decision:** The repo is a data pipeline with agents on top, published as FL's own GitHub project (not a fork).
- **Why:** DE interviewers care about ingestion, modeling, orchestration and data quality. A fork reads as someone else's work, and forks of public repos are always public.
- **Alternatives:** Fork ai-job-search (rejected: portfolio and privacy reasons).

### #3 · 2026-10-27 · Storage: Postgres + S3 backup
- **Decision:** Postgres in Docker for all data; raw JD files backed up nightly to S3 in FL's personal AWS account.
- **Why:** The search may run 6–12 months. Airflow needs Postgres anyway. Postgres handles several writers at once (pipeline, API, dashboard); DuckDB allows only one writer. S3 backup survives a laptop failure for pennies.
- **Alternatives:** DuckDB (single-writer locking), S3 + Athena only (cost and setup slow down week 1).

### #4 · 2026-10-27 · Orchestration: Python first, Airflow later
- **Decision:** Write each pipeline step as a plain Python function; run them with a simple daily script first, then wrap the same functions in Airflow DAGs.
- **Why:** Gets data flowing in week 1 with no rewrite later. Airflow is the most common orchestration keyword in DE job descriptions.
- **Alternatives:** Airflow from day 1 (slower start), Dagster (less common in JDs).

### #5 · 2026-10-27 · Anthropic API key for agents
- **Decision:** FL creates her own Anthropic API key (with a monthly spending limit) so the repo's agents run independently.
- **Why:** The repo must run on its own and be runnable by anyone who clones it.

### #6 · 2026-10-27 · Job sources
- **Decision:** Greenhouse, Lever and freehire.me public APIs, plus LinkedIn public (logged-out) job listings.
- **Why:** ATS APIs cover most small companies with structured data. LinkedIn covers big tech. FL specifically likes the LinkedIn and freehire sources from ai-job-search.
- **Constraint:** Automated LinkedIn access is against LinkedIn's terms. Keep it low-volume and personal-use; ship it behind a flag that is off by default in the public repo. Never automate FL's logged-in LinkedIn account.

### #7 · 2026-10-27 · Company strategy
- **Decision:** Start with small companies (startups, under ~500 people) as **interview practice**. The real goal is big tech, which opens up once practice interviews and the coverage report show readiness.

### #8 · 2026-10-27 · Apply bar ~50%
- **Decision:** Apply when roughly 50% of a JD's must-haves are covered by skills FL has or is actively using in projects.
- **Why:** Postings are wish lists; FL is learning fast and wants volume of good-enough matches.

### #9 · 2026-10-27 · Keyword rule ("advertise, not invent")
- **Decision:** Read the JD first and use its exact keywords on the resume, polished onto FL's real experience.

| JD keyword | FL's situation | What we do |
| --- | --- | --- |
| "data pipelines" | Did it, called it "ETL jobs" | Rewrite in the JD's words |
| "Airflow" | Touched it a little (project, adjacent tool at work) | Add it, framed as strongly as the experience allows |
| "Kafka" | Never touched | Leave it off; shows as "not covered" in the coverage report |

- **Why:** FL's view: this is marketing yourself, not lying. Never-touched tools and inflated years are excluded because they collapse in a technical screen.
- **Differs from ai-job-search**, which leaves out anything the profile doesn't clearly support.

### #10 · 2026-10-27 · Submission flow
- **Decision:** Claude in Chrome fills each application up to the final review page; FL approves the batch in chat ("submit all" / "submit 1, 3, 5"); then Claude clicks Submit.
- **Constraints (Claude's limits, not negotiable):** Claude does not enter passwords, create accounts, solve CAPTCHAs or submit without an explicit yes. FL logs in once per site; Chrome keeps the session. LinkedIn Easy Apply stays manual.
- **Why:** FL wants to study while applications go out; this keeps her time to ~2 minutes a day.

### #11 · 2026-10-27 · Resume output
- **Decision:** One-page PDF compiled from a template, with a compile-and-inspect layout loop and an ATS text-layer check (text extracted from the final PDF).
- **Open:** template engine (LaTeX, as ai-job-search uses, or Typst, which is lighter). Decide in week 2.

### #12 · 2026-10-27 · Borrow from ai-job-search
- **Decision:** Adapt these MIT-licensed pieces instead of rebuilding them, with credit: JD safety gate, drafter-reviewer loop, PDF compile-and-inspect, ATS text-layer check, LinkedIn and freehire search tools, interview-prep and outcome-tracking patterns.
- **Why:** Proven in a real job search; frees our time for what it lacks (data pipeline, US sources, submit queue, outreach, coverage report).

### #13 · 2026-10-27 · Agent 9 is a coverage report, not a study plan
- **Decision:** The daily report answers "do my current + in-progress skills cover most target jobs?" (coverage score, top-10 skills marked have / learning / not covered, best-fit segments). It does not recommend what to study.

### #14 · 2026-10-27 · Skill files location
- **Decision:** Agent rules live in `.claude/skills/<name>/SKILL.md`. Claude Code picks them up automatically, and the API code loads the same files, so there is one source of truth.

### #15 · 2026-10-27 · Docs are the memory
- **Decision:** `CLAUDE.md` + `docs/STATUS.md` + `docs/DECISIONS.md` are read at the start of every session and updated at the end. Copies of DESIGN, DECISIONS and STATUS are also uploaded to the "Job Hunting" claude.ai Project so chats there stay in sync. **The repo copy is the master.**

### #16 · 2026-10-28 · Build first, real resume last
- **Decision:** Build and test the whole system before touching FL's real resume. Development uses a fake sample profile in `data/sample/` (a made-up DE-transition candidate: resume, Evidence Bank, Applicant Profile) in exactly the formats the real files will use. FL's real material is plugged in at Milestone 5 as just another input, by pointing the config from `data/sample/` to `private/`.
- **Why:** FL wants the system finished first; the resume is only an input. The sample profile also keeps the public repo runnable and demo-able without any personal data.
- **Note:** The applications themselves start at Milestone 5, not week 1 as earlier planned.

### #17 · 2026-10-28 · Public repo doesn't name FL or her employer
- **Decision:** Committed files refer to her only as "FL" and to her employer only generically ("a large tech company", "FL's current employer"). The real name and employer live only in `private/` (resume, Evidence Bank, Applicant Profile).
- **Why:** The repo is public and its history is permanent; it shouldn't tell coworkers she is job hunting. Agent rules work the same with the employer read from the Evidence Bank.
- **Alternatives:** Name and employer in the open (fine once the repo link goes on her resume; can be revisited then).

### #18 · 2026-10-28 · How each ai-job-search piece is borrowed
- **Decision:** Copy the two Python tools (JD safety gate, PDF text-layer check); port the TypeScript LinkedIn and freehire clients to Python; borrow only the idea for the layout check, drafter-reviewer loop, interview prep and outcome tracking. Full table in `docs/DESIGN.md`. Copied or ported files carry an MIT header; the full license is in `LICENSES/ai-job-search-MIT.txt`. Reference clone pinned at commit `83c788d`.
- **Why:** Copy where their code is already Python and hard to match (the gate covers many hidden-text tricks); port so the repo stays one language FL can explain; ideas only where theirs is prompt prose or tied to their LaTeX template and Poppler.
- **Alternatives:** Vendor their code as-is with bun (two languages in the repo); git submodule (would ship their skills and commands into ours).

### #19 · 2026-10-30 · Python environment: uv
- **Decision:** Manage Python 3.12 and dependencies with uv (`pyproject.toml` + committed `uv.lock`, environment in the project's `.venv/`). Add dependencies only when a milestone needs them; Airflow runs in Docker, not in this environment.
- **Why:** The machine only had Anaconda's Python 3.9. uv installs 3.12 for this project without touching Anaconda, the lockfile makes the environment reproducible for anyone who clones the repo, and `uv run` needs no environment activation (one less terminal step for FL).
- **Alternatives:** A Python 3.12 conda environment in the existing Anaconda (lives outside the project, no standard lockfile, needs `conda activate`); plain venv + pip (no Python version management, no lockfile).

### #20 · 2026-10-30 · JD safety gate: copy unchanged, wrap, measure before tuning
- **Decision:** The detection logic is copied into `pipeline/posting_guard.py` unchanged (only the CLI and file reading removed) together with their tests; our interface is `pipeline/safety_gate.py` (`run_gate()` → `GateResult` with cleaned text, findings, verdict, `alarmed`, `gate_version`). The rules are not tuned yet: once ingestion has a few hundred real postings, measure how many alarm and why (the known false positive is ssh/curl/.env in honest skill lines), then decide. Every stored result carries `GATE_VERSION`, so a rule change means re-running the gate from raw, not editing old results. How alarmed postings reach agents is decided in M2 (current plan: agents read only `cleaned_text`; alarmed postings are held for FL to look at).
- **Why:** An unchanged copy plus their tests proves our version behaves like theirs and keeps upstream fixes easy to compare. Tuning by measured false-positive rate instead of by guess. Raw stays immutable; derived results are recomputable.
- **Alternatives:** One merged file (harder to compare with upstream); loosening the ssh/curl rule now (no data yet on how often it fires).

### #21 · 2026-10-30 · Raw layer: versions by content hash, daily sightings, run log
- **Decision:** Ingestion stores every job on each configured board (not only DE titles) in four tables: `raw.job_postings` (one row per distinct content version, payload as returned, never updated; a new row only when a hash of the content fields changes, so volatile fields like Greenhouse `updated_at` don't create versions), `raw.job_sightings` (one row per job per UTC day seen), `raw.ingest_runs` (one row per board per run, with outcome and counts), and `gate.results` (one row per posting version per `GATE_VERSION`). Schema changes are numbered SQL files in `db/migrations/`, applied once each. Each board loads in one transaction; a failing board is recorded and the rest continue. Boards live in `config/companies.toml`; the M1 starter list is 19 mostly mid-size and large boards chosen only because they answered and had DE-type roles. Default DB host is `127.0.0.1`.
- **Why:** Raw stays an immutable record that everything downstream can be rebuilt from; content-hash versions make the load idempotent and keep edit history; sightings give first/last seen and time-open without duplicating payloads; the run log makes failures visible. Filtering to DE roles belongs in dbt staging, where it can change without re-fetching. `localhost` made every connection several seconds slower on Windows (IPv6 tried first).
- **Alternatives:** Upsert one row per job (loses history, needs updates to raw); insert every fetch (duplicates daily, breaks idempotency); hash the whole payload (a new version every time `updated_at` moves); a migration framework like Alembic (more than we need now).

### #22 · 2026-10-30 · Deterministic decisions, AI proposes, rules change only through a loop
- **Decision:** Runtime judgments are made by code with versioned rules, never by an agent on the fly. First use: alarm triage. Every gate result gets a tier: `clean` (no alarm), `benign` (visible line flagged only by weak rules, no steering words, no other signal), `review` (visible but not clearly harmless) or `block` (anything hidden: instruction words in hidden content, invisible or tag text, word-splitting characters). Weak rules and steering words live in `config/triage_rules.toml` (version 1); instruction patterns are referred to by stable names (`pipeline/alarm_triage.py RULE_SIGNATURES`). The stored gate version is detection version + rules version (`d1-t1`), so any rules change recomputes everything from raw while old results stay. The golden set `tests/fixtures/gate_cases.jsonl` (39 cases: 5 real false positives, 25 attacks, plus clean and look-alike cases) must hold for any rules change, and no attack may come out benign or clean. Rules change only through the loop: report → FL labels → an agent (Claude, in Claude Code for now) proposes a change → the change is evaluated against all labeled cases and all stored postings → FL approves → version bump → recompute → entry here. Step B of this (labels table, evaluation command) comes next. The same pattern applies to LLM steps in M2: outputs cached by (input hash, prompt version, model) and evaluated against golden sets before a prompt or model change.
- **Why:** Same input + same rules = same answer, so results are explainable and repeatable, and every change is visible in a diff and reversible. Letting an agent change rules on its own would let rules drift unseen and would let an attacker loosen them by feeding harmless-looking data first (data poisoning). The benign tier is deliberately narrow; hidden content is always blocked because real attacks hide.
- **Alternatives:** Hand-review every alarm (doesn't scale to new sources); let an LLM judge each alarm at runtime (non-deterministic, itself injectable); let an agent auto-update rules from labels (drift and poisoning).
- **Result:** On the 2300 real postings, rules v1 give clean 2286, benign 14, review 0, block 0.
