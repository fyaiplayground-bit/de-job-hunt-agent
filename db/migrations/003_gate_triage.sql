-- Triage tier for every gate result (decision #22). Rows written before triage existed (gate
-- version "1") keep null; the gate step re-checks every posting under the new version.

alter table gate.results
    add column triage         text check (triage in ('clean', 'benign', 'review', 'block')),
    add column triage_reasons jsonb;
