-- Safety gate results, derived from raw.job_postings. Recomputable: when the gate's rules
-- change, GATE_VERSION goes up and every posting version is checked again from raw.

create schema if not exists gate;

create table gate.results (
    posting_version_id bigint not null references raw.job_postings (posting_version_id),
    gate_version       text not null,
    cleaned_text       text not null,  -- the only text agents may read
    findings           jsonb not null,
    verdict            text not null,
    alarmed            boolean not null,
    checked_at         timestamptz not null default now(),
    primary key (posting_version_id, gate_version)
);
