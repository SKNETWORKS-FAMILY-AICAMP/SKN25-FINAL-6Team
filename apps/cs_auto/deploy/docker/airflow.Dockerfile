FROM apache/airflow:2.10.5-python3.12

ENV PYTHONPATH=/opt/airflow/dags:/opt/airflow/dags/apps/cs_auto/backend:/opt/airflow/dags/apps/weekly_report \
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
        pkg-config \
    && rm -rf /var/lib/apt/lists/*

USER airflow

COPY --chown=airflow:root common /opt/airflow/dags/common
COPY --chown=airflow:root apps/cs_auto/backend /opt/airflow/dags/apps/cs_auto/backend
COPY --chown=airflow:root apps/weekly_report /opt/airflow/dags/apps/weekly_report
COPY --chown=airflow:root data /opt/airflow/data
COPY --chown=airflow:root apps/cs_auto/deploy/scripts/start-airflow.sh /usr/local/bin/start-airflow

COPY --chown=airflow:root apps/cs_auto/backend/requirements.txt /tmp/cs-auto-requirements.txt
RUN python -m pip install --no-cache-dir -r /tmp/cs-auto-requirements.txt \
    && python -m pip install --no-cache-dir -r /opt/airflow/dags/apps/weekly_report/requirements.txt \
    && chmod +x /usr/local/bin/start-airflow
