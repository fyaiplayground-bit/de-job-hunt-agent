-- Every wording that leads to a skill in the current profile (its names and aliases, and the
-- vocabulary's synonyms and families it covers), so dbt can say have, learning or not covered
-- (decision #41). Copied on every analytics run, because the real profile must stay out of the
-- public repo and so can't be a dbt seed.

create table agents.profile_skills (
    term_key            text primary key,   -- a wording, lowercased
    skill               text not null,
    status              text not null check (status in ('have', 'learning')),
    level               text,
    profile_fingerprint text not null,
    updated_at          timestamptz not null default now()
);
