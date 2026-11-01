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

### #23 · 2026-10-30 · Rules loop step B: labels, evaluation, proposals
- **Decision:** A person's judgment is stored in `gate.labels` (append-only; the newest label per posting wins; keeps the gate version, tier and flagged lines that were judged). `pipeline.labels export` turns labels into golden cases in `tests/fixtures/gate_cases_labeled.jsonl`: only the flagged line, never the whole posting; identical lines merged; hidden lines re-hidden and invisible text re-spelled so each case reproduces its tier; unsure labels left out. `pipeline.evaluate_rules <proposal>` judges every golden case and every stored posting under the current and proposed rules, read-only. Hard checks (fail = reject): every hand-written case in its expected tier, no attack (hand or labeled) benign or clean, no labeled false positive blocked. Soft: share of labeled false positives that are benign. Proposals live in `config/proposals/` and replace the rules file only after FL approves. Walked once on real data: 14 false positives labeled → 5 cases; an "everything weak" proposal and a "weaken chat_template_token" proposal were both rejected (the second showed 0 changed postings and was caught only by the golden set); a comment-only proposal passed with 0 changes. Rules stay at v1: no data asks for a change.
- **Why:** Labels make judgments durable and reusable; evaluation makes "what would this change do" a command instead of a promise. Only the flagged line is exported because postings are other companies' text in a public repo. Real postings alone can't show a loosened rule's risk, since they only contain what has already happened.
- **Alternatives:** Labels as a CSV in the repo (no link to the exact gate result judged); evaluating against stored postings only (missed the template-token weakening); changing rules now to demonstrate the loop (contradicts "change rules only when data asks").

### #24 · 2026-10-31 · Search sources (freehire, LinkedIn), request budgets, exact cross-source dedupe
- **Decision:** Ingestion targets are either boards (`config/companies.toml`) or saved searches (`config/searches.toml`); the run log names the target (`raw.ingest_runs.target`) and counts requests. freehire is ported from ai-job-search (MIT header): one saved search (US, data/analytics engineer titles), paged up to `max_pages`, daily window 2 days; payload stored as returned; volatile fields (counters, `reality`, `last_seen_at`, utm URL) excluded from the content hash. LinkedIn is ported for parsing only (not their browser-like User-Agent/headers), **off by default** (`LINKEDIN_PUBLIC_ENABLED`), with a hard per-UTC-day request cap enforced from the run log across runs; known jobs are not re-fetched (sighting only); raw payload is the HTML returned. No live LinkedIn request has been made; the first one needs FL's OK. Cross-source dedupe v1 is exact and lives in views (`dedupe.job_identity`, `dedupe.jobs`): identity = ATS/board/job id, freehire's `external_id` (`board:id`) maps Greenhouse/Lever jobs to the same key, the direct ATS copy wins. Fuzzy matching (needed for LinkedIn) is a later step with versioned rules and golden pairs. `pipeline.discover_boards` lists Greenhouse/Lever boards seen via freehire that aren't configured; FL picks what to add.
- **Why:** One aggregator search reaches many ATSs and small companies that board-guessing can't. Exact identity keys are deterministic and explainable; views keep dedupe recomputable until dbt (M3). The request cap makes "low volume, personal use" a property of the code, not a promise.
- **Alternatives:** Keyword-filtering board pulls only (misses most companies); fuzzy dedupe now (needs its own rules loop); storing a dedupe table (another thing to keep in sync).
- **First real run:** freehire 7-day backfill hit the 5000-job cap (incomplete), 4592 distinct; the next run added 224 genuinely new jobs. 7118 raw postings → 7073 jobs (45 found by both Greenhouse and freehire). freehire marks 22% of jobs stale. Gate: review 4, block 5, all apparent false positives, pending FL's labels (rules loop).
- **Fix in the same step:** `dedupe.jobs` v1 used correlated subqueries (didn't finish in 20 s at ~7k rows); migration 007 rewrites it to group once (0.59 s), same columns.

### #25 · 2026-10-31 · HTTP identity: learn from ai-job-search, but don't imitate a site
- **Decision:** Take from ai-job-search's LinkedIn client what is good practice: the conventional crawler User-Agent format (`Mozilla/5.0 (compatible; de-job-hunt-agent/0.1; +<repo url>)`, the same shape as Googlebot's, naming us), `Accept` / `Accept-Language` headers, random jitter on retry backoff (Retry-After still honored exactly), and skipping a job whose LinkedIn detail page is 404 instead of failing the whole search. Don't take the `X-Requested-With: XMLHttpRequest` header, which makes requests look like they come from LinkedIn's own pages. The first live LinkedIn request is made with this honest setup; if LinkedIn blocks it, the step pauses for FL with the data, and any move toward imitation would first need the CLAUDE.md hard rule changed.
- **Why:** FL wanted to use their proven approach. Most of it is ordinary good HTTP practice and is now adopted. The one imitating header conflicts with the "no anti-detection code" hard rule, raises account and repo risk while job hunting, and hasn't been shown to be needed: no live request has been made yet.
- **Alternatives:** Copy their headers wholesale (conflicts with the hard rule, untested need); keep our earlier non-conventional UA (some sites reject it, and the conventional format is just as honest).

### #26 · 2026-10-31 · Triage rules v2: zero-width editing artifacts no longer block
- **Decision:** Adopt `config/proposals/triage_rules.v2.toml` as `config/triage_rules.toml` (version 2). New switch `zero_width_artifacts_not_blocked = true`: zero-width characters inside words, with no instruction-like line, no invisible text, no tag characters and no bidi characters, are benign ("editing artifact") instead of block. Everything else is unchanged. The first full turn of the rules loop on real data: FL labeled 9 alarms from the first freehire run as false positives (3 Axon anti-phishing notices and 1 Schneider SSH line stay in review, on purpose: the strong rule "ignore the..." and whole-line steering check catch real attack shapes; 5 zero-width artifacts were blocked). Label export now caps long lines at the excerpt around the trigger (no whole description in the public repo) and reproduces zero-width words from the posting (tags stripped first).
- **Why:** 5 of 5 blocks were copy-paste leftovers (`stor|y`, `our |h|eadquarters`). The gate already removes these characters before scanning, so with nothing else suspicious they hide nothing. Evaluation: hard checks PASS; labeled false positives benign 6 → 12 of 13; postings changed: exactly the 5 labeled ones, block → benign; nothing else moved. Still blocked under v2 (tested): zero-width characters splitting an instruction, any bidi override, zero-width plus invisible text.
- **Alternatives:** Keep v1 (blocks honest postings and contradicts confirmed labels); sentence-scoped steering check for the Schneider case (would let the "steering words after the cut" attack through — rejected by the golden set); weakening "ignore the..." for the Axon case (it also catches "ignore the above and run the following").
- **Result:** All 7,118 postings recomputed from raw under `d1-t2`: clean 7,089, benign 25, review 4, block 0. Old `d1-t1` results kept.

### #27 · 2026-10-31 · Daily run: local now, cloud later
- **Decision:** `uv run python -m pipeline.daily` is the one daily command: connect (if Postgres doesn't answer, start Docker Desktop once and wait up to 3 minutes), take a Postgres advisory lock (a second run exits), fetch every enabled target, run the gate, write `output/daily/<date>.md` and `output/daily/latest.md` (gitignored, local only), and record the run in `ops.daily_runs`. Search window = days since the last ok/partial daily run + 1, kept within 2–7, so a laptop that was off catches up. "New" is defined by this run's ingest run ids (a job is new when every copy of it was stored by this run), not by clocks. `run_daily()` is a plain function; Windows Task Scheduler calls it now through `scripts/daily.cmd`, and an Airflow or cloud scheduler can call the same function later. Schedule: 8:30 a.m. America/Los_Angeles (the laptop's own time zone), run as soon as possible after a missed start, allowed on battery, no wake-from-sleep. FL reads the report through a desktop shortcut; Claude summarizes the last run at the start of each session. Creating the scheduled task and the shortcut needs FL's explicit OK.
- **Why:** FL expects to move to the cloud but wants to start locally; keeping Windows only in the trigger layer makes that move a scheduler swap. The adaptive window closes the gap a fixed 2-day window would leave after days offline. Run ids make "new today" exact and testable.
- **Alternatives:** Fixed 2-day window (misses jobs after a few days off); wake-from-sleep (unreliable on a closed laptop); cloud now (needs a cloud database, which is M4 scope); pop-up notifications (FL prefers the desktop shortcut).
- **First real runs:** run 1 ok in 80 s (1 new job), run 2 ok (1 new job: Coinbase posted new roles in between); a third started during run 2 exited on the lock.
- **Schedule superseded by #29** (9:30 a.m. instead of 8:30); everything else stands.

### #28 · 2026-10-31 · Candidate profile format: structured TOML, Evidence Bank as the single source of truth
- **Decision:** The profile the agents read is three files in the folder named by `PROFILE_DIR` (`data/sample` until Milestone 5, then `private`): `evidence_bank.toml` (roles, projects, education, one `[[evidence]]` entry per thing done with skills, level `production | project | practiced`, metrics, a `rounded` flag and an interview story, plus a `[skills]` table with canonical names, aliases and status `have | learning`), `applicant_profile.toml` (contact, links, work authorization, notice period, salary floor and target, work modes and office cities, background and EEO answers) and `resume.md` (the untailored master resume, one column, headings Summary / Experience / Projects / Skills / Education). A skill's level is computed as the strongest level among its evidence, not typed. `agents/profile.py` loads and checks them (`uv run python -m agents.profile check [folder]`); the resume must trace to the Evidence Bank (titles, employers and dates match the roles; every Skills item resolves to a skill; every number in Summary and bullets appears in some metric). The public sample is the fictional Alex Sample (BI engineer → DE) with built-in test cases for the agents (alias rewrite, lightly touched Airflow, learning Spark, never-touched Kafka/Scala, rounded numbers, dealbreakers), guarded by a test that allows only `example.com` addresses and 555-01xx phone numbers. `resume_current.pdf` and `project_summaries/` in `private/` stay raw material that Claude distills into these files; agents don't read them.
- **Why:** Decision #22: matching a JD's "Airflow" to the candidate's "Apache Airflow" and deciding a skill's level must be code with the same answer every time, which needs structured data rather than prose. TOML is readable, takes comments, has no indentation traps, is in the Python standard library (`tomllib`) and is already used for the triage rules. Checking the resume against the Evidence Bank is the ats-critic's evidence check done up front, on the source files.
- **Alternatives:** Markdown (pleasant to read, but only an LLM can pull fields out of it); JSON (no comments, easy to break by hand); YAML (indentation-sensitive, extra dependency); computing levels by hand (drifts from the evidence).

### #29 · 2026-11-01 · Daily run moves to 9:30 a.m.
- **Decision:** The scheduled task runs at 9:30 a.m. local time (America/Los_Angeles, stored without a UTC offset so it follows daylight saving). All other settings from #27 stay: catch-up after a missed start, allowed on battery, no wake-from-sleep, one instance at a time, 1-hour limit.
- **Why:** FL's request after the first scheduled run (8:30 on 2026-11-01) was missed: the laptop slept from 9:21 p.m. until 9:03 a.m. A later time makes it likelier the laptop is awake; a missed run is caught by the catch-up setting and, failing that, by the session-start check.
- **Alternatives:** Wake the laptop to run (rejected in #27: unreliable on a closed laptop); keep 8:30.

### #30 · 2026-11-01 · Agent layer: the LLM reads and drafts, code scores and decides; Typst; Opus 5.5
- **Decision:** Milestone 2 splits each agent step between an LLM and code. The LLM does only what needs reading or writing: jd-analysis extracts a JSON brief (must-haves, exact phrases, archetype, location, remote policy, pay); resume-tailoring drafts by selecting and rewording Evidence Bank entries; a reviewer in a fresh context proposes edits (at most two rounds). Code does every judgment: matching JD skills to the profile by name and alias, the fit score and its decision (the formula in `fit-scoring/SKILL.md`, no LLM call), dealbreakers from the Applicant Profile, checking every drafted skill and number against the Evidence Bank (the `agents.profile` checks), and the ATS checks on the PDF text layer. Resumes are rendered with **Typst** (installed as a Python package through uv, no system install), pending a check that it installs and renders here (step 2.4). Default model **`claude-opus-5-5`** at effort **`medium`** (`LLM_MODEL`, `LLM_EFFORT` in `.env`), with server-side fallback (`fallbacks: "default"`) so a safety decline is retried on the model Anthropic recommends; `served_model` records who answered.
- **Plumbing (step 2.1):** `agents/skills.py` loads each `.claude/skills/<name>/SKILL.md` as a system prompt with a `version:` line; `config/prompt_lock.toml` records each version and a SHA-256 of the text, and a test fails when the text changes without a bump, so prompts change only through the rules loop (#22). `agents/llm.py` builds every request the same way (skill + a fixed "data, not instructions" rule as system prompt, the posting inside `<data>` tags with any `</data>` defused, JSON schema through structured outputs, system prompt marked for prompt caching) and stores each answer in `agents.llm_calls` keyed by a hash of the whole request, with prompt version, input hash, model, served model, tokens and cost. The same request is answered from the table. Refusals, cut-off answers and answers missing required fields raise and are not stored. `FakeClient` stands in for the API in tests. Commands: `agents.llm ping` (one tiny uncached live call), `agents.llm costs`, `agents.skills check | lock`.
- **Why:** #22 asks that the same input and versions give the same output; an LLM can't promise that, a cache keyed by the full request can, and scores computed by code need no cache at all. Keeping the LLM to reading and drafting also limits what a prompt-injected posting could steer. Typst avoids a multi-gigabyte LaTeX install and has a simpler template language; both give a text layer an ATS reads. Opus 5.5 is the current default model; effort `medium` keeps cost down for extraction and can be raised per run.
- **Alternatives:** LLM-judged fit scores (non-deterministic, steerable by the posting); LaTeX (heavy install, as ai-job-search uses); a file-based cache (Postgres is already there and queryable for costs); Sonnet 5.5 or Haiku 5.5 to save money (can be switched in `.env` after measuring on the golden set); no fallback (a decline would stop the run).
- **Cost estimate (before measuring):** about $0.03–0.06 to analyze one posting, $0.3–0.5 per tailored resume; FL's monthly spending limit on the Console caps it.
