-- Application tracking (decision #57): FL can withdraw an application, at any point from approval
-- to an offer. The other statuses after "applied" were allowed from the start (014).
alter table agents.application_events drop constraint application_events_status_check;
alter table agents.application_events add constraint application_events_status_check
    check (status in (
        'awaiting_approval', 'approved', 'passed', 'applied', 'recruiter_screen', 'tech_screen',
        'onsite', 'offer', 'rejected', 'ghosted', 'withdrawn'
    ));
