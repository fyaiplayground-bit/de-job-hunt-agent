-- A person's judgment of an alarmed posting (rules loop step B, decision #23). Append-only: a
-- new label for the same posting supersedes the old one, which stays as history.

create table gate.labels (
    label_id           bigserial primary key,
    posting_version_id bigint not null references raw.job_postings (posting_version_id),
    label              text not null check (label in ('false_positive', 'attack', 'unsure')),
    note               text,
    labeled_by         text not null,
    labeled_at         timestamptz not null default now(),
    gate_version       text not null,   -- the rules that produced the alarm being judged
    tier_at_label      text not null,   -- what those rules said: benign / review / block
    flagged_lines      jsonb not null   -- the lines the person read, as shown in the report
);

create index labels_by_posting on gate.labels (posting_version_id, labeled_at desc);
