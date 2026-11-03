-- One fit score per brief, profile and rule set (decision #35). Computed by code from
-- agents.jd_briefs and the candidate profile, so it costs nothing to recompute: a new profile
-- (its fingerprint changes), new scoring rules or a new vocabulary version adds rows, and old
-- scores stay for comparison.

create table agents.fit_scores (
    posting_version_id  bigint not null references raw.job_postings (posting_version_id),
    brief_prompt_version text not null,      -- the jd-analysis brief this score read
    brief_model         text not null,
    profile_fingerprint text not null,       -- SHA-256 of the three profile files
    rules_version       integer not null,    -- config/fit_scoring.toml
    vocabulary_version  integer not null,    -- config/skill_vocabulary.toml
    score               integer not null check (score between 0 and 100),
    decision            text not null check (decision in ('apply_referral', 'apply', 'skip')),
    result              jsonb not null,      -- coverage, matched skills, dealbreakers, lead_with
    created_at          timestamptz not null default now(),
    primary key (posting_version_id, brief_prompt_version, brief_model, profile_fingerprint,
                 rules_version, vocabulary_version)
);
