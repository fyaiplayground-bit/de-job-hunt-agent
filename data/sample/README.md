# data/sample/: the fictional sample profile

**Everything in this folder is made up.** Alex Sample, Quillfeather Outdoor, Brightmoor Logistics, Front Range State University, the bike-share project and every number are fictional. Contact details use reserved values (`example.com`, phone 555-01xx). Any resemblance to a real person or company is accidental.

The whole system is built and tested against this profile (decision #16). At Milestone 5 the real files go into `private/` in exactly these formats, and `PROFILE_DIR` in `.env` changes from `data/sample` to `private` (decision #28).

## Files

| File | Holds | Read by |
| --- | --- | --- |
| `evidence_bank.toml` | Work history, projects, education, one entry per thing done (skills used, level, numbers, interview story), and the skill list with aliases and have / learning status. **The only source of facts.** | fit-scoring, resume-tailoring, ats-critic, coverage-report |
| `applicant_profile.toml` | Contact, links, work authorization, notice period, salary floor and target, work modes and cities, EEO answers | Application forms and knockout questions; fit-scoring dealbreakers |
| `resume.md` | The current, untailored master resume: one column, standard headings | resume-tailoring (starting point) |

The resume is a view of the Evidence Bank: every skill in its Skills section and every number in its bullets must trace back to an entry. Check all three files with:

```
uv run python -m agents.profile check
```

## The candidate

Business Intelligence Engineer at an online outdoor-gear retailer since 2021, Data Analyst at a freight company before that, moving into data engineering. Strong in SQL, Redshift, Glue, Athena and dimensional modeling at work; dbt, Postgres and Docker in a personal pipeline project; Airflow only tried; Spark being learned.

## Built-in test cases for the agents (Milestone 2)

| Case | Where | What the agents should do |
| --- | --- | --- |
| Same work, different words | Resume says "ETL jobs"; many JDs say "data pipelines" (an alias of `ETL`) | Rewrite in the JD's words (decision #9) |
| Touched lightly | `Apache Airflow`: one practice DAG (`practiced`), not on the resume | Add it when a JD asks, framed as strongly as the evidence allows |
| Learning | `Apache Spark`: status `learning`, course exercises only | Counts toward coverage; fit-scoring records level `practiced` |
| Never touched | Kafka, Scala, Snowflake, Java: no entry | Never on a resume; listed in `not_covered` |
| Rounded internal number | `qf-athena-clickstream`, `qf-data-quality` (`rounded = true`) | Use the rounded form only |
| Dealbreakers | Salary floor 120000; remote or hybrid in Denver/Boulder; no sponsorship needed | Skip onsite-only jobs elsewhere and jobs below the floor |
