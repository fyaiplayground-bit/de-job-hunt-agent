-- Every Claude API call the agents make (decision #30), kept as a cache and a cost log.
-- request_hash fingerprints the whole request (model, effort, system prompt, output schema,
-- user input), so the same request is answered from here instead of the API: re-runs cost
-- nothing and give the same answer. prompt_version and input_hash say which skill version and
-- which input produced a row, for evaluation and recompute (decision #22).

create schema if not exists agents;

create table agents.llm_calls (
    llm_call_id        bigserial primary key,
    request_hash       text not null unique,
    prompt_name        text not null,          -- the skill, e.g. jd-analysis
    prompt_version     text not null,          -- e.g. jd-analysis@1
    model              text not null,          -- the model asked for
    served_model       text not null,          -- the model that answered (differs after a fallback)
    effort             text not null,
    input_hash         text not null,
    output             jsonb not null,
    stop_reason        text not null,
    input_tokens       integer not null,
    output_tokens      integer not null,       -- includes thinking tokens
    cache_read_tokens  integer not null default 0,
    cache_write_tokens integer not null default 0,
    cost_usd           numeric(10, 6),         -- null when the model's price is unknown
    request_id         text,
    created_at         timestamptz not null default now()
);

create index llm_calls_prompt_input on agents.llm_calls (prompt_name, prompt_version, input_hash);
create index llm_calls_created_at on agents.llm_calls (created_at);
