FROM apache/airflow:2.10.5-python3.12

ENV PYTHONPATH=/opt/airflow/packages/common-python/src:/opt/airflow/cs_auto_backend \
    AIRFLOW__CORE__LOAD_EXAMPLES=False \
    AIRFLOW__CORE__DAGS_FOLDER=/opt/airflow/cs_auto_backend/airflow

COPY --chown=airflow:root apps/cs_auto/backend/requirements.txt /tmp/cs-auto-requirements.txt
RUN python -m pip install --no-cache-dir -r /tmp/cs-auto-requirements.txt

COPY --chown=airflow:root packages/common-python/src /opt/airflow/packages/common-python/src
COPY --chown=airflow:root apps/cs_auto/backend /opt/airflow/cs_auto_backend
