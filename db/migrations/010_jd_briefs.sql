-- One structured brief per posting version, per jd-analysis prompt version and model
-- (decision #31). The brief is the LLM's answer (stored in agents.llm_calls) plus the company,
-- title and URL that code copied from the raw posting. fit-scoring reads only this table.
-- A new prompt version or model adds rows; old briefs stay for comparison.

create table agents.jd_briefs (
    posting_version_id bigint not null references raw.job_postings (posting_version_id),
    prompt_version     text not null,          -- e.g. jd-analysis@2
    model              text not null,
    scope_version      integer not null,       -- config/analysis_scope.toml version that chose it
    llm_call_id        bigint not null references agents.llm_calls (llm_call_id),
    brief              jsonb not null,
    created_at         timestamptz not null default now(),
    primary key (posting_version_id, prompt_version, model)
);
