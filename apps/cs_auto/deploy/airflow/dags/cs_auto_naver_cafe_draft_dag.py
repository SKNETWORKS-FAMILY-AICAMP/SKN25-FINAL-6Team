from __future__ import annotations

import pendulum
from airflow.decorators import dag, task

from batch.airflow_jobs import run_naver_cafe_draft_batch


SEOUL = pendulum.timezone("Asia/Seoul")


@dag(
    dag_id="cs_auto_naver_cafe_draft_daily",
    schedule="0 3 * * *",
    start_date=pendulum.datetime(2026, 6, 2, tz=SEOUL),
    catchup=False,
    tags=["cs_auto", "answer_draft", "naver_cafe"],
)
def cs_auto_naver_cafe_draft_daily():
    @task(task_id="run_naver_cafe_draft")
    def run_naver_cafe_draft() -> dict:
        return run_naver_cafe_draft_batch(limit=500)

    run_naver_cafe_draft()


dag = cs_auto_naver_cafe_draft_daily()
