"""Create Airflow's own database next to the job data, once (decision #46).

Airflow keeps its records (DAG runs, task states, logs index) in a database called "airflow" on
the same Postgres server, so they never mix with the pipeline's tables. Runs in the airflow-init
container with Airflow's Python, which ships psycopg2.
"""

import os

import psycopg2

conn = psycopg2.connect(
    host=os.environ["POSTGRES_HOST"],
    port=os.environ["POSTGRES_PORT"],
    dbname=os.environ["POSTGRES_DB"],
    user=os.environ["POSTGRES_USER"],
    password=os.environ["POSTGRES_PASSWORD"],
)
conn.autocommit = True  # create database can't run inside a transaction
with conn.cursor() as cur:
    cur.execute("select 1 from pg_database where datname = 'airflow'")
    if cur.fetchone() is None:
        cur.execute("create database airflow")
        print("created database airflow")
    else:
        print("database airflow already exists")
conn.close()
