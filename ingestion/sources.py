"""Registry of job sources. Each source module provides the same functions:

    fetch_jobs(ctx, target)   -> list of job dicts, exactly as the source returned them
    job_id(job)               -> the source's own id for the job, as text
    company(job, target)      -> the company: the board token for board sources, from the job
                                 itself for search sources
    posting_html(job)         -> title + description as HTML, for the safety gate
    content_fields(job)       -> the fields that define the posting's content, for change detection

Board sources (greenhouse, lever) are listed in config/companies.toml; search sources (freehire,
linkedin) in config/searches.toml. Adding a source means one module with these functions, listed
here.
"""

from types import ModuleType

from ingestion import freehire, greenhouse, lever, linkedin

SOURCES: dict[str, ModuleType] = {
    greenhouse.NAME: greenhouse,
    lever.NAME: lever,
    freehire.NAME: freehire,
    linkedin.NAME: linkedin,
}


def get_source(name: str) -> ModuleType:
    try:
        return SOURCES[name]
    except KeyError:
        raise ValueError(f"unknown source {name!r}; known: {sorted(SOURCES)}") from None
