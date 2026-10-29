# de-job-hunt-agent

A data-engineering pipeline that ingests job postings daily, models skill demand with dbt, and feeds a team of Claude-powered agents that analyze each role, tailor a one-page resume, check it like an ATS, and report how well the candidate's skills cover the market.

**Status:** under construction — see [`docs/STATUS.md`](docs/STATUS.md).

## Stack

Python · Postgres · dbt · Airflow · FastAPI · Streamlit · Claude API · AWS S3

## Docs

- [`docs/DESIGN.md`](docs/DESIGN.md) — architecture and agents
- [`docs/DECISIONS.md`](docs/DECISIONS.md) — every design decision and why

## Credits

The agent layer adapts ideas from the MIT-licensed [ai-job-search](https://github.com/ai-job-search-dev/ai-job-search) framework.
