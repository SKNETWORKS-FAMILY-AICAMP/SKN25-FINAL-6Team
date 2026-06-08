"""Scheduled Airflow DAG for the CS analysis agent."""

from __future__ import annotations

import sys
from pathlib import Path

import pendulum
from airflow.decorators import dag, task

# Airflow가 DAG 파일을 별도 경로에서 로드할 수 있으므로,
# backend 디렉터리를 import 경로에 추가해 agents 패키지를 찾게 한다.
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from agents.analysis_agent import run_analysis_agent  # noqa: E402


# 모든 스케줄은 한국 시간 기준으로 실행한다.
KST = pendulum.timezone("Asia/Seoul")
DEFAULT_ARGS = {"owner": "cs_auto"}


# 매일 새벽 1시에 문의 분석 agent를 실행하는 DAG.
@dag(
    dag_id="cs_auto_analysis_agent_daily",
    schedule="0 1 * * *",
    start_date=pendulum.datetime(2026, 1, 1, tz=KST),
    catchup=False,
    default_args=DEFAULT_ARGS,
    tags=["cs_auto", "analysis"],
)
def analysis_agent_daily_dag() -> None:
    """Run the analysis agent every day at 01:00 KST."""

    # 실제 분석 로직은 agents.analysis_agent.run_analysis_agent 안에서 구현한다.
    @task(task_id="run_analysis_agent")
    def run_scheduled_analysis_agent() -> None:
        run_analysis_agent()

    run_scheduled_analysis_agent()


# Airflow가 모듈을 import할 때 DAG 객체를 발견할 수 있도록 인스턴스화한다.
analysis_agent_daily = analysis_agent_daily_dag()
