FROM apache/airflow:2.10.5-python3.12

ENV PYTHONPATH=/opt/airflow/dags/packages/common-python/src:/opt/airflow/dags/apps/cs_auto/backend:/opt/airflow/dags/apps/weekly_report \
    AIRFLOW__CORE__LOAD_EXAMPLES=False \
    AIRFLOW__CORE__DAGS_FOLDER=/opt/airflow/dags \
    CS_AUTO_KEYWORD_DIR=/opt/airflow/data/keywords \
    CS_AUTO_SQL_DIR=/opt/airflow/data/sql

USER root

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        fontconfig \
        fonts-nanum \
        libcairo2-dev \
        libpango-1.0-0 \
        libpangoft2-1.0-0 \
        libpangocairo-1.0-0 \
        libharfbuzz0b \
        libgdk-pixbuf-2.0-0 \
        pkg-config \
    && rm -rf /var/lib/apt/lists/*

USER airflow

COPY --chown=airflow:root packages/common-python/src /opt/airflow/dags/packages/common-python/src
COPY --chown=airflow:root packages/common-python/pyproject.toml /opt/airflow/dags/packages/common-python/pyproject.toml
COPY --chown=airflow:root apps/cs_auto/backend /opt/airflow/dags/apps/cs_auto/backend
COPY --chown=airflow:root apps/weekly_report /opt/airflow/dags/apps/weekly_report
COPY --chown=airflow:root data/sql /opt/airflow/data/sql
COPY --chown=airflow:root data/keywords /opt/airflow/data/keywords

COPY --chown=airflow:root apps/cs_auto/backend/requirements.txt /tmp/cs-auto-requirements.txt
RUN python -m pip install --no-cache-dir /opt/airflow/dags/packages/common-python \
    && python -m pip install --no-cache-dir -r /tmp/cs-auto-requirements.txt \
    && tail -n +2 /opt/airflow/dags/apps/weekly_report/requirements.txt >/tmp/weekly-report-requirements.txt \
    && python -m pip install --no-cache-dir -r /tmp/weekly-report-requirements.txt
