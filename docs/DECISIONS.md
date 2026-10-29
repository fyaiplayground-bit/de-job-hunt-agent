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
