"""Unit tests for the source modules and change detection. No network, no database."""

from ingestion import greenhouse, lever
from pipeline.load import content_hash


def test_greenhouse_job_id_is_text(greenhouse_jobs):
    assert greenhouse.job_id(greenhouse_jobs[0]) == "1001"


def test_greenhouse_posting_html_is_unescaped_and_has_the_title(greenhouse_jobs):
    page = greenhouse.posting_html(greenhouse_jobs[0])

    assert page.startswith("<h1>Data Engineer</h1>")
    assert "<strong>Python</strong>" in page
    assert "&lt;" not in page


def test_greenhouse_title_is_escaped_so_it_cannot_inject_markup(greenhouse_jobs):
    job = greenhouse_jobs[0]
    job["title"] = "Data Engineer <div style='display:none'>x</div>"

    assert "<div" not in greenhouse.posting_html(job).split("</h1>")[0]


def test_updated_at_alone_does_not_change_the_hash(greenhouse_jobs):
    job = greenhouse_jobs[0]
    before = content_hash(greenhouse.content_fields(job))
    job["updated_at"] = "2026-11-30T09:00:00-04:00"

    assert content_hash(greenhouse.content_fields(job)) == before


def test_a_content_edit_changes_the_hash(greenhouse_jobs):
    job = greenhouse_jobs[0]
    before = content_hash(greenhouse.content_fields(job))
    job["content"] += "&lt;p&gt;Now hybrid.&lt;/p&gt;"

    assert content_hash(greenhouse.content_fields(job)) != before


def test_department_order_does_not_change_the_hash(greenhouse_jobs):
    job = greenhouse_jobs[0]
    job["departments"] = [{"name": "B"}, {"name": "A"}]
    before = content_hash(greenhouse.content_fields(job))
    job["departments"] = [{"name": "A"}, {"name": "B"}]

    assert content_hash(greenhouse.content_fields(job)) == before


def test_lever_posting_html_joins_sections_in_page_order(lever_postings):
    page = lever.posting_html(lever_postings[0])

    order = [
        page.index("<h1>Analytics Engineer</h1>"),
        page.index("own our dbt project"),
        page.index("<h3>What you&#x27;ll do</h3>"),
        page.index("<h3>Requirements</h3>"),
        page.index("Compensation"),
    ]
    assert order == sorted(order)


def test_lever_hash_ignores_created_at(lever_postings):
    job = lever_postings[0]
    before = content_hash(lever.content_fields(job))
    job["createdAt"] = 1
    job["applyUrl"] = "https://elsewhere.example"

    assert content_hash(lever.content_fields(job)) == before
