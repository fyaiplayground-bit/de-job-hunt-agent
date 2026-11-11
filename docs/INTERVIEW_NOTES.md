# Interview notes

How to explain each milestone in an interview: plain English first, then the detail an engineer will probe. First person, because FL is the one saying it. Raw material lives in `docs/NOTES.md` section 6; the reasons behind each choice are in `docs/DECISIONS.md` (numbers in brackets).

---

## Milestone 1 · Skeleton + ingestion (done 2026-10-31)

### The 30-second version

> "I built a daily ingestion pipeline for job postings. It pulls from three public sources (Greenhouse and Lever APIs for 19 companies, plus an aggregator, freehire) into Postgres. Raw JSON is stored unchanged and versioned by content hash, so re-runs are idempotent. Every posting passes a prompt-injection safety gate before any LLM may read it, and the gate's decisions come from versioned rules that change only through an evaluation loop, much like evals in ML. Cross-source duplicates are resolved in SQL views. It runs itself every morning with a lock, an adaptive look-back window and a run log. About 7,100 postings so far, 270 tests."

### What it looks like

```
Greenhouse / Lever / freehire  (LinkedIn built, off by default)
   │  ingestion/  fetch, request budgets, retries
   ▼
raw.job_postings   one row per distinct version (content hash), JSON never modified
raw.job_sightings  one row per posting per day seen  →  "how long was it open?"
raw.ingest_runs    one row per source per run        →  one failure doesn't stop the others
   │  pipeline/safety_gate.py + alarm_triage.py (rules: config/triage_rules.toml)
   ▼
gate.results       verdict per posting version AND per rules version (old results kept)
   │
dedupe.*           SQL views: one job, even if it arrived from two sources
   │
pipeline.daily     one command: lock → fetch → gate → report → ops.daily_runs
```

### Stories worth telling (pick two or three)

**1. Idempotent raw layer [#21].** Raw JSON is immutable. A posting gets a new version only when its content hash changes; I left volatile fields like `updated_at` out of the hash, because otherwise every posting would look "changed" every day. Content and daily sightings are separate tables, so I don't store duplicates but can still compute how long a job stayed open. *Demo:* run the same day twice; the second run adds 0.

**2. Safety gate + rules loop: evals for a deterministic system [#20, #22, #23, #26].** Job postings are untrusted input that an LLM will read later, so hidden text and instruction-like lines are a prompt-injection risk. I adopted an open-source detector unchanged (ported its 59 tests to prove identical behavior) and wrapped it. On the first 2,300 real postings it raised 14 alarms (0.6%), all false positives, e.g. "You are an AI pragmatist" in a culture paragraph. Instead of hand-tuning, I made triage deterministic: code sorts alarms into clean / benign / review / block, rules live in a versioned TOML file, and a golden set of labeled cases (real false positives plus known attack shapes) gates every change. The loop: report → label → propose → evaluate against every labeled case and every stored posting (no known attack may come out benign) → approve → bump version → recompute from raw, keeping old results.
- *Why it matters:* one deliberately weakened proposal showed "0 postings changed" on real data and looked harmless; only the golden set caught it. Real data covers only what has already happened.
- *First real turn:* a new source brought 9 alarms; 5 were zero-width characters left by copy-paste. Once labeled, the current rules contradicted the labels in tests. Rules v2 added one narrow switch; evaluation showed exactly those 5 postings moved. Recomputed 7,118 postings: block 0.

**3. Cross-source dedupe [#24].** The aggregator re-lists jobs I also fetch directly. I dedupe on a deterministic identity key (ATS + board + job id) and prefer the copy closest to the source. 7,118 raw records → 7,073 jobs. Raw keeps every copy; dedupe is a derived view, so it can be rebuilt.

**4. A SQL performance fix [#24].** My first dedupe view used a correlated subquery and didn't finish in 20 seconds at 7,000 rows. I measured it, rewrote it as group-then-join (0.59 s), and shipped it as a new migration instead of editing one that had already run, so every database ends up the same.

**5. Daily run design [#27].** One plain Python function, so Windows Task Scheduler today and Airflow or a cloud scheduler later call the same code. A Postgres advisory lock prevents overlapping runs. The look-back window adapts to the last successful run (2–7 days), so a laptop that was off for days catches up. "New today" is defined by run ids, not clocks, which made it exact and testable.

**6. Responsible scraping [#6, #25].** LinkedIn is off by default, has a hard daily request cap stored in the database (it holds across runs), never re-requests a job already stored, and identifies itself honestly: no browser imitation, no anti-detection.

**7. Data contract for the candidate profile [#28].** The agents in Milestone 2 read a resume, an Evidence Bank and an Applicant Profile. I made them structured TOML with a validator: the Evidence Bank is the single source of truth, and the resume is a view of it. Every skill and every number on the resume must trace to an Evidence Bank entry, which works like referential integrity. Matching a JD's "Airflow" to "Apache Airflow" is a deterministic alias lookup, not an LLM guess. Everything is built against a fictional sample profile, so the public repo runs without personal data.

### Numbers to remember

| | |
| --- | --- |
| Sources | Greenhouse + Lever (19 boards), freehire; LinkedIn built, off |
| Postings | ~7,100 raw → 7,073 jobs after dedupe |
| Gate | First run: 14 alarms / 2,300 postings (0.6%), all false positives; now block 0 |
| Golden set | 13 labeled real cases + hand-written attack shapes |
| Tests | 270 (unit tests always run; DB tests skip when Postgres is down) |
| Slow query | > 20 s → 0.59 s; test suite 69 s → 2 s (Windows tried IPv6 first for `localhost`) |
| Data quality | Aggregator flags 22% of its postings as stale or reposted; kept in raw for modeling |

### Questions to expect

- **"Why Postgres and not DuckDB?"** Several writers at once (pipeline, API, dashboard, Airflow's own metadata); DuckDB allows one writer [#3].
- **"Why not Airflow from day one?"** Plain functions first got data flowing in week 1; Airflow DAGs will call the same functions in Milestone 4 with no rewrite [#4].
- **"What does idempotent mean here, concretely?"** Re-running a day stores nothing new: versions are keyed by content hash, sightings by (posting, date). There's a test for it, and I demonstrated it on real data.
- **"How do you know your rules change didn't break anything?"** The evaluation command compares proposed vs current rules on every labeled case and every stored posting, and fails if any known attack becomes benign. Old results are kept by version, so a change is reversible.
- **"Why not let an LLM judge the alarms?"** Same input must give the same output, and a model can be steered by the very text it is judging. The LLM may propose rule changes; code decides, and a human approves [#22].
- **"What would you do differently?"** Set `statement_timeout` before running a heavy query (I found the slow view only through a timeout), and record the scheduler's time zone explicitly (a trigger saved with a fixed DST offset would have run an hour early after November 1).

### Talking about AI assistance honestly

I designed the system and made every decision recorded in `DECISIONS.md`; I used Claude Code as a pair programmer to write much of the code. Be ready to walk through any file, and say "I built it with an AI pair programmer, and here's why it's designed this way" rather than hiding it.

---

## Milestone 2 · Agents (done 2026-11-04)

### The 30-second version

> "On top of the pipeline I built an agent layer that reads each job posting, scores the fit, and writes a tailored one-page resume, then queues it for my approval. The rule I held to: the LLM reads and drafts, code decides. Scores, dealbreakers and every fact on the resume are checked by plain code, so the same input gives the same output, and an LLM can't invent a title or a number."

### What an engineer will probe

- **How do you keep LLM output deterministic?** Every call is stored in Postgres under a hash of the whole request, so a re-run is answered from the table at no cost. Prompts are versioned files, and a test fails if the text changes without a version bump. Scoring has no LLM at all.
- **How do you stop it making things up?** The LLM can't reach the facts: name, titles, employers and dates are filled in by code from an Evidence Bank. Each bullet must cite its evidence, and its numbers must be in the metrics of what it cites, so even a true number from another job is rejected. A second LLM reviews with fresh context, but its edits go through the same checks. I'm honest about the limit: code can't catch overstated tone, so a person still reads the result.
- **How do you evaluate prompts?** A golden set of 13 real postings with labels. Early on a new prompt failed: it looked as if it had lost skills. Reading the source showed the skills were there in a merged form my scorer couldn't read, so I fixed the scorer and measured old and new with the same ruler. The evaluation also proved a cheaper setting was just as good, and it is why a prompt change never ships unmeasured.
- **Tell me about a bug the data found.** A user reading the results asked why a good job scored only 58. "dbt, Snowflake, BigQuery, or similar" had been split into three must-haves, so the two tools the candidate lacked counted as gaps. A rough scan flagged 47 of 87 briefs, including jobs wrongly skipped. I changed the prompt so either/or lines are one requirement, added those cases to the golden set, and checked 10 real jobs against their source text before adopting it.
- **Data modeling choice?** The approval queue stores each queued job as one immutable row and its status as an append-only event log, with a view for the current state. The whole history is kept, and the application funnel can be built straight from it.
- **Safety?** Postings are untrusted input. They pass a safety gate first and go to the LLM as data, never as instructions; the resume drafter doesn't read the posting at all, only a structured brief. A batch built from the fictional profile is locked by code so it can't be marked as sent.

### Numbers worth quoting

- About 16,800 postings stored; about 900 in scope for the AI step at any time, filtered by code first because reading one costs about $0.04.
- About $0.18 for a checked one-page resume, measured on real jobs, against an estimate of $0.30-0.50.
- 44 labeled wordings for the security clearance rule; 2,462 data engineering postings as a wider test.

---

## Milestone 3 · Modeling + reporting (done 2026-11-04)

### The 30-second version

> "On top of the raw data I built a dbt project with three layers: staging flattens each source's JSON, a skills layer gets one row per skill per job, and marts answer business questions: which skills the market wants, what share of jobs my skills cover, and how my applications are going. It rebuilds daily with data tests, and a Streamlit dashboard reads only the marts."

### What an engineer will probe

- **Why three layers?** Each has one job. Staging only cleans, with no business logic; if a source changes its JSON, one model changes. The skills layer holds the grain I analyze. Marts are shaped for one question each, so the dashboard stays simple.
- **What's the grain of the skills table?** One row per job per skill named. "Python or Java" gives two rows, so demand for each is counted, and "Data pipelines" and "ETL pipelines" share a key through a seeded vocabulary. Separately, one row per requirement says whether my profile covers it, because those are different questions.
- **Why doesn't dbt compute the fit score?** The score is a business rule already in tested Python. Recomputing it in SQL would give two definitions that drift, so dbt reads the stored result. The same logic made me keep the dedupe view where it is: the daily pipeline depends on it.
- **Tell me about a bug tests didn't catch.** All tests passed and the numbers were wrong. My fictional candidate showed as having Snowflake and Java, and 87 jobs fell on one date. I only saw it by reading the output against what I knew. The first was deriving a skill's status from whether a requirement was covered; I switched to the same name resolution the scorer uses. The second was a UTC date in a Los Angeles report. Tests check what you thought of; someone still has to look at the numbers.
- **How do you handle private data in a public repo?** The real profile can't be a dbt seed. Code copies it into a database table at run time, so it never reaches git, and a test checks the only seed is the public vocabulary.
- **What if dbt fails?** The daily run catches it and says so in the report; ingestion is unaffected, because the analytics schemas can always be rebuilt from raw.

### Numbers worth quoting

- 56 dbt steps (models, seed, data tests) on about 16,800 postings; AI step adds no cost here, since everything is SQL over stored results.
- Top must-haves in 87 postings so far: SQL 76%, Python 66%, ETL 61%, data modeling 49%. Say the sample size out loud: it's small, and the report prints it for that reason.

## Milestone 4 · Production polish (done 2026-11-10)

### The 30-second version

> "I made the pipeline something I'd trust unattended. The daily run is split into steps that each save their result, so the same functions run in one process from the Windows scheduler or as separate tasks in an Airflow DAG, and a failed step can be retried alone. Every night a dump goes to S3 under a key that can't delete anything, and once a month I restore it into a scratch database and compare row counts, because a backup you haven't restored isn't a backup."

### What an engineer will probe

- **How do Airflow tasks share state?** Each step writes its part of the summary and what later steps need (ingest run ids, new job ids) to `ops.daily_run_steps`. Airflow only passes the run id between tasks (XCom). Keeping state in the database, not in Airflow, means the Windows path and the DAG share one copy of the logic, and a retried fetch keeps the ids of the try that half-worked.
- **Why BashOperator calling a CLI instead of PythonOperator?** The pipeline has its own environment built from the same `uv.lock` as the laptop. Airflow pins its own packages and dbt pins others; keeping them apart means neither has to agree with the other, and a crash in my code can't take the worker down.
- **How did you roll it out?** In shadow mode: triggered by hand, writing its report to a separate folder, with a `runner` column on every run and a guard so the two schedulers never run at once. The comparison found a real bug: the backup shelled out to `docker exec`, and there's no Docker inside the Airflow container. I installed the client tools matching the server version (not the newer ones in the image, whose dumps the old tools may not read), reran just the backup step, and restored that dump on the other side.
- **Why didn't Airflow take over the schedule?** Running it always on costs about 1 GB of memory on a laptop that sleeps, and for one daily pipeline the Windows task does the job. Airflow earns its place with many dependent pipelines, backfills by data date and a team that needs one place to see failures. On AWS, for one daily job, I'd likely use EventBridge to trigger it rather than keep a scheduler running.
- **What's the backup's blast radius if the key leaks?** The IAM policy allows put, get and list on one bucket, no delete; old backups expire through a lifecycle rule the key can't change. Before each upload the code checks the account id, so a work profile on the same machine can never receive the data.
- **What's the restore test exactly?** Download the dump, `pg_restore` into a temporary database, compare row counts of the main tables with the live ones taken at dump time, drop the temporary database.

### Numbers worth quoting

- 12 Airflow tasks; a whole day ran in under 3 minutes with the four sources fetched in parallel (briefing 6 new jobs).
- Daily dump ~84 MB (rebuildable analytics schemas excluded); 30-day expiry on daily copies, monthly copies kept.
- 658 automated tests, including ones that run the steps one at a time the way Airflow does and check they give the same numbers as one in-process run.

