from __future__ import annotations

import pendulum
from airflow.decorators import dag, task

from batch.airflow_jobs import run_ticket_analysis_batch


SEOUL = pendulum.timezone("Asia/Seoul")


@dag(
    dag_id="cs_auto_ticket_analysis_daily",
    schedule="0 2 * * *",
    start_date=pendulum.datetime(2026, 6, 2, tz=SEOUL),
    catchup=False,
    tags=["cs_auto", "ticket_analysis"],
)
def cs_auto_ticket_analysis_daily():
    @task(task_id="run_ticket_analysis")
    def run_ticket_analysis() -> dict:
        return run_ticket_analysis_batch(limit=500)

    run_ticket_analysis()


dag = cs_auto_ticket_analysis_daily()
