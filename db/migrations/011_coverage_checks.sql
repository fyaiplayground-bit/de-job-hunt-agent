-- Coverage checks (decision #34): every time FL finds a job somewhere else (e.g. on LinkedIn) and
-- asks whether the pipeline has it, the answer is logged here. found / checked is the pipeline's
-- measured recall; the reason column says what to fix when a job was missed.

create table ops.coverage_checks (
    coverage_check_id bigserial primary key,
    checked_at        timestamptz not null default now(),
    company_query     text not null,
    title_query       text not null,
    found             boolean not null,
    reason            text not null check (reason in (
        'found',              -- stored by the pipeline
        'freehire_title',     -- freehire has it, but its title is outside our search terms
        'freehire_missed',    -- freehire has it and the title fits: window, page cap or timing
        'board_missing',      -- one of our boards, but the job isn't stored
        'not_in_freehire',    -- no source of ours has it
        'unknown'             -- the live freehire check failed
    )),
    matches           jsonb not null,   -- stored postings that matched
    freehire_matches  jsonb,            -- what the live freehire search returned, when it ran
    note              text
);
