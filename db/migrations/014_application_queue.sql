-- The approval queue (decision #40). A queued job is one row that never changes; its status lives
-- in an append-only event log, so the history of every application is kept and the funnel in
-- Milestone 3 can be built straight from it.

create table agents.queue_items (
    posting_version_id  bigint primary key references raw.job_postings (posting_version_id),
    batch_date          date not null,
    batch_number        integer not null,   -- the number FL says: "approve 1, 3, 5"
    sample              boolean not null,   -- built from the fictional profile: can never be applied
    profile_fingerprint text not null,
    rules_version       integer not null,   -- config/queue.toml
    company_key         text not null,      -- normalized, to find the same company again
    job_key             text not null,      -- normalized company + title
    title_key           text not null,      -- normalized title + application site
    snapshot            jsonb not null,     -- what the page and the pack show, as it was then
    created_at          timestamptz not null default now(),
    unique (batch_date, batch_number)
);

create table agents.application_events (
    event_id            bigserial primary key,
    posting_version_id  bigint not null references agents.queue_items (posting_version_id),
    status              text not null check (status in (
        'awaiting_approval', 'approved', 'passed', 'applied', 'recruiter_screen', 'tech_screen',
        'onsite', 'offer', 'rejected', 'ghosted'
    )),
    reason              text,               -- why FL passed, or anything else worth keeping
    created_at          timestamptz not null default now()
);

create index on agents.application_events (posting_version_id, event_id);

-- Each queued job with its latest status.
create view agents.applications as
select i.*, e.status, e.reason, e.created_at as status_at
from agents.queue_items i
join lateral (
    select status, reason, created_at from agents.application_events a
    where a.posting_version_id = i.posting_version_id
    order by event_id desc limit 1
) e on true;
