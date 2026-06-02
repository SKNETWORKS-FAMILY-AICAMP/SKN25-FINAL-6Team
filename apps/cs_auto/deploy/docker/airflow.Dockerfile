FROM apache/airflow:2.10.5-python3.12

USER root

COPY packages/common-python /opt/gameops/packages/common-python
COPY apps/cs_auto/deploy/airflow/requirements.txt /tmp/cs-auto-airflow-requirements.txt

USER airflow

RUN python -m pip install --no-cache-dir /opt/gameops/packages/common-python \
    && python -m pip install --no-cache-dir -r /tmp/cs-auto-airflow-requirements.txt
