FROM apache/airflow:2.10.5-python3.12

USER root

COPY packages/common-python /opt/gameops/packages/common-python
COPY apps/cs_auto/backend /opt/gameops/apps/cs_auto/backend
COPY apps/cs_auto/deploy/airflow/dags /opt/airflow/dags
COPY apps/cs_auto/deploy/airflow/requirements.txt /tmp/cs-auto-airflow-requirements.txt
RUN chown -R airflow:0 /opt/gameops /tmp/cs-auto-airflow-requirements.txt

USER airflow

RUN python -m pip install --no-cache-dir /opt/gameops/packages/common-python \
    && python -m pip install --no-cache-dir -r /tmp/cs-auto-airflow-requirements.txt

ENV PYTHONPATH=/opt/gameops/packages/common-python/src:/opt/gameops/apps/cs_auto/backend

WORKDIR /opt/gameops
