"""Registry of job sources. Each source module provides the same four functions:

    fetch_jobs(client, token) -> list of job dicts, exactly as the API returned them
    job_id(job)               -> the source's own id for the job, as text
    posting_html(job)         -> title + description as HTML, for the safety gate
    content_fields(job)       -> the fields that define the posting's content, for change detection

Adding a source (freehire next) means writing one module with these functions and listing it here.
"""

from types import ModuleType

from ingestion import greenhouse, lever

SOURCES: dict[str, ModuleType] = {
    greenhouse.NAME: greenhouse,
    lever.NAME: lever,
}


def get_source(name: str) -> ModuleType:
    try:
        return SOURCES[name]
    except KeyError:
        raise ValueError(f"unknown source {name!r}; known: {sorted(SOURCES)}") from None
