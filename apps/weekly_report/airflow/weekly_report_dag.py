"""Airflow DAG for the weekly report pipeline."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pendulum
from airflow.decorators import dag, task

from common.observability.langfuse import configure_langfuse


_APP_DIR = Path(__file__).resolve().parents[1]
_REPO_ROOT = _APP_DIR.parents[1]

for _path in (_APP_DIR, _REPO_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

KST = pendulum.timezone("Asia/Seoul")
configure_langfuse("weekly-report", default_tags=["weekly-report", "airflow"])

DEFAULT_ARGS = {"owner": "weekly_report"}


def materialize_insight_rows() -> int:
    from db.insight import sync_insight_rows

    return sync_insight_rows()


def run_weekly_report_job() -> None:
    channel = os.environ.get("DASHBOARD_WEEKLY_REPORT_CHANNEL", "").strip()
    if not channel:
        raise ValueError("DASHBOARD_WEEKLY_REPORT_CHANNEL environment variable is required.")
    comment = os.environ.get("DASHBOARD_WEEKLY_REPORT_COMMENT", "").strip() or None

    import report as report_module

    report_module.run(
        days=7,
        render_pdf=True,
        send_to_slack=True,
        slack_channel=channel,
        slack_comment=comment,
    )


@dag(
    dag_id="dashboard_weekly_report",
    schedule="0 9 * * 1",
    start_date=pendulum.datetime(2026, 1, 1, tz=KST),
    catchup=False,
    default_args=DEFAULT_ARGS,
    tags=["weekly_report"],
)
def weekly_report_dag() -> None:
    @task(task_id="materialize_insight_rows")
    def materialize_insight_rows_task() -> int:
        return materialize_insight_rows()

    @task(task_id="run_weekly_report")
    def run_weekly_report_task() -> None:
        run_weekly_report_job()

    materialize_insight_rows_task() >> run_weekly_report_task()


dashboard_weekly_report = weekly_report_dag()
