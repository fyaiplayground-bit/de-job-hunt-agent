-- Search sources (decision #24): a run fetches a target that is either a board (one company) or
-- a saved search (many companies), so the run log names the target, not a company. It also
-- counts requests, which is how LinkedIn's per-day request cap is enforced across runs.

alter table raw.ingest_runs rename column company to target;

alter table raw.ingest_runs
    add column requests_made integer,
    add column note text;  -- e.g. "request budget used up"; not an error
