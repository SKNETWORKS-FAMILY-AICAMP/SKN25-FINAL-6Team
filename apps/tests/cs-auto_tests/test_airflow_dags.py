from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path


def test_cs_auto_answer_agent_daily_dag_imports_with_expected_schedule(monkeypatch) -> None:
    """Airflow 설치 여부와 무관하게 DAG 파일의 import 계약을 검증한다.

    CI/로컬 단위 테스트 환경에는 Apache Airflow가 없을 수 있다. 이 테스트는
    decorators와 pendulum만 최소 fake로 주입해 DAG 파일이 분석/답변 agent를
    import하고, 답변 DAG가 04:00 KST 스케줄로 인스턴스화되는지 확인한다.
    """

    airflow_module = types.ModuleType("airflow")
    decorators_module = types.ModuleType("airflow.decorators")

    def fake_dag(**dag_kwargs):
        def decorator(func):
            def wrapper(*args, **kwargs):
                return {"dag_id": dag_kwargs["dag_id"], "schedule": dag_kwargs["schedule"], "factory": func.__name__}

            wrapper.__dag_kwargs__ = dag_kwargs
            return wrapper

        return decorator

    def fake_task(task_id):
        def decorator(func):
            def wrapper(*args, **kwargs):
                return {"task_id": task_id, "factory": func.__name__}

            return wrapper

        return decorator

    pendulum_module = types.ModuleType("pendulum")
    pendulum_module.timezone = lambda name: name
    pendulum_module.datetime = lambda *args, **kwargs: {"args": args, "kwargs": kwargs}
    decorators_module.dag = fake_dag
    decorators_module.task = fake_task

    monkeypatch.setitem(sys.modules, "airflow", airflow_module)
    monkeypatch.setitem(sys.modules, "airflow.decorators", decorators_module)
    monkeypatch.setitem(sys.modules, "pendulum", pendulum_module)

    root_dir = Path(__file__).resolve().parents[3]
    dag_path = root_dir / "apps" / "cs_auto" / "backend" / "airflow" / "cs_auto_agent_dags.py"
    spec = importlib.util.spec_from_file_location("cs_auto_agent_dags_import_test", dag_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.analysis_agent_daily["dag_id"] == "cs_auto_analysis_agent_daily"
    assert module.analysis_agent_daily["schedule"] == "0 1 * * *"
    assert module.answer_agent_daily["dag_id"] == "cs_auto_answer_agent_daily"
    assert module.answer_agent_daily["schedule"] == "0 4 * * *"
