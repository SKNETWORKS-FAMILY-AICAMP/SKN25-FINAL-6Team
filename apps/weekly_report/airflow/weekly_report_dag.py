"""Airflow DAG: 주간 운영 리포트 자동 실행 (매주 월요일 09:00 KST)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pendulum
from airflow.decorators import dag, task

# 현재 파일(apps/weekly_report/airflow/)을 기준으로 모듈 경로를 등록한다.
# cs_auto와 병합하여 DAG 파일 위치가 바뀌면 아래 두 경로 상수를 갱신한다.
_APP_DIR = Path(__file__).resolve().parents[1]           # apps/weekly_report/
_COMMON_DIR = _APP_DIR.parents[1] / "packages" / "common-python" / "src"

for _p in (_APP_DIR, _COMMON_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

KST = pendulum.timezone("Asia/Seoul")

# cs_auto 병합 시: owner → "cs_auto", tags에 "cs_auto" 추가
DEFAULT_ARGS = {"owner": "weekly_report"}


@dag(
    dag_id="dashboard_weekly_report",
    schedule="0 9 * * 1",  # 매주 월요일 09:00 KST
    start_date=pendulum.datetime(2026, 1, 1, tz=KST),
    catchup=False,
    default_args=DEFAULT_ARGS,
    tags=["weekly_report"],
)
def weekly_report_dag() -> None:
    """매주 월요일 09:00 KST 주간 운영 리포트를 생성하여 Slack으로 전송한다."""

    @task(task_id="run_weekly_report")
    def run_weekly_report() -> None:
        """report.run()으로 전체 파이프라인을 실행한다 (데이터 수집 → PDF → Slack)."""
        channel = os.environ.get("DASHBOARD_WEEKLY_REPORT_CHANNEL", "").strip()
        if not channel:
            raise ValueError(
                "DASHBOARD_WEEKLY_REPORT_CHANNEL 환경변수가 설정되지 않았습니다."
            )
        comment = os.environ.get("DASHBOARD_WEEKLY_REPORT_COMMENT", "").strip() or None

        import report as report_module  # sys.path 설정 완료 후 런타임 임포트

        report_module.run(
            days=7,
            render_pdf=True,
            send_to_slack=True,
            slack_channel=channel,
            slack_comment=comment,
        )

    run_weekly_report()


# Airflow가 모듈 import 시 DAG 객체를 발견할 수 있도록 인스턴스화한다.
dashboard_weekly_report = weekly_report_dag()
