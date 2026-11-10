# Airflow plus the pipeline's own Python environment (decision #46).
#
# Airflow schedules; the pipeline's steps run in a separate environment at /opt/jobhunt-venv,
# built from the same uv.lock as the laptop's, so the two sets of packages never clash. The code
# itself is not copied in: docker-compose mounts the repo at /opt/jobhunt, so a code change
# needs no rebuild. Only pyproject.toml and uv.lock enter the build (see .dockerignore), so
# private/ and .env can never end up inside the image.
FROM apache/airflow:3.3.2-python3.12

COPY --from=ghcr.io/astral-sh/uv:0.13.6 /uv /usr/local/bin/uv

USER root
# pg_dump/pg_restore matching the Postgres 17 server, for the backup step: on Windows it runs them
# inside the Postgres container through Docker; here it reaches the server over the network.
# (The image ships version 18, whose dumps the 17 tools may not read back.)
RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client-17 \
    && apt-get clean && rm -rf /var/lib/apt/lists/*
# /usr/python is the image's base Python (Airflow's own packages live in /home/airflow/.local).
ENV UV_PROJECT_ENVIRONMENT=/opt/jobhunt-venv \
    UV_PYTHON=/usr/python/bin/python3.12 \
    UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1
WORKDIR /opt/jobhunt-build
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project && rm -rf /root/.cache/uv

USER airflow
WORKDIR /opt/airflow
