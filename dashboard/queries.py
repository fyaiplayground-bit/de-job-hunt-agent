"""What the dashboard reads: the dbt marts, nothing else. Read-only."""

import pandas as pd

from pipeline.db import connect

QUERIES = {
    "coverage": "select * from analytics_marts.mart_coverage_summary order by period_order",
    "archetypes": "select * from analytics_marts.mart_coverage_by_archetype order by 2 desc",
    "skills": "select * from analytics_marts.mart_skill_frequency order by rank",
    "funnel": "select * from analytics_marts.mart_funnel order by stage_order",
    "pipeline": "select * from analytics_marts.mart_pipeline_daily order by local_date",
    "costs": "select * from analytics_marts.mart_ai_costs order by local_date, prompt_name",
}
SAMPLE_QUERY = "select bool_or(sample) from agents.queue_items"
PROFILE_QUERY = "select count(*) from agents.profile_skills"


def load_all() -> dict[str, pd.DataFrame]:
    with connect() as conn, conn.cursor() as cursor:
        tables = {}
        for name, query in QUERIES.items():
            cursor.execute(query)
            columns = [column.name for column in cursor.description]
            tables[name] = pd.DataFrame(cursor.fetchall(), columns=columns)
    for frame in tables.values():
        for column in frame.columns:
            if frame[column].map(type).astype(str).str.contains("Decimal").any():
                frame[column] = pd.to_numeric(frame[column])
    return tables
