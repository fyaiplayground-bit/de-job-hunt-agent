-- One tailored resume per job, profile and prompt versions (decision #38). The LLM answers are
-- cached in agents.llm_calls, so re-running with the same inputs rebuilds the same row for free.

create table agents.tailored_resumes (
    posting_version_id      bigint not null references raw.job_postings (posting_version_id),
    profile_fingerprint     text not null,   -- SHA-256 of the three profile files
    tailor_prompt_version   text not null,   -- resume-tailoring@N
    reviewer_prompt_version text not null,   -- resume-reviewer@N
    model                   text not null,
    status                  text not null check (status in ('ready', 'needs_review')),
    review_rounds           integer not null,
    draft                   jsonb not null,  -- the final content: headline, summary, bullets, skills
    resume_md               text not null,   -- what code built from the draft
    problems                jsonb not null,  -- what the checks still report; empty when ready
    history                 jsonb not null,  -- each review round: edits applied and rejected, trims
    pdf_path                text not null,
    cost_usd                numeric(10, 6) not null,  -- what the LLM calls behind this row cost
    created_at              timestamptz not null default now(),
    primary key (posting_version_id, profile_fingerprint, tailor_prompt_version,
                 reviewer_prompt_version, model)
);
