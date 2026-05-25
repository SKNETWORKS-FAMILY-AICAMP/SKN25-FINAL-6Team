"""Run the dashboard FastAPI server and Streamlit UI together."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import urlopen

from dotenv import load_dotenv

# .env 로드: os.environ.copy() 전에 실행해야 LangSmith 변수가 서브프로세스 env에 포함된다
load_dotenv()

ROOT_DIR = Path(__file__).resolve().parents[2]
API_HOST = os.environ.get("DASHBOARD_API_HOST", "127.0.0.1")
API_PORT = os.environ.get("DASHBOARD_API_PORT", "8010")
FRONTEND_HOST = os.environ.get("DASHBOARD_FRONTEND_HOST", "127.0.0.1")
FRONTEND_PORT = os.environ.get("DASHBOARD_FRONTEND_PORT", "8510")
API_BASE_URL = f"http://{API_HOST}:{API_PORT}"


def wait_for_api() -> None:
    for _ in range(30):
        try:
            with urlopen(f"{API_BASE_URL}/health", timeout=1) as response:
                if response.status == 200:
                    return
        except OSError:
            time.sleep(1)
    raise RuntimeError(f"dashboard API did not start: {API_BASE_URL}")


def main() -> None:
    env = os.environ.copy()
    env["DASHBOARD_API_BASE_URL"] = API_BASE_URL
    # LangSmith 프로젝트를 dashboard 전용으로 고정해 operation 트레이스와 분리한다
    env["LANGSMITH_PROJECT"] = "skn25-dashboard"

    api_process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "src.dashboard.api.main:app",
            "--host",
            API_HOST,
            "--port",
            API_PORT,
        ],
        cwd=ROOT_DIR,
        env=env,
    )
    wait_for_api()

    frontend_process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            "src/dashboard/frontend/app.py",
            "--server.address",
            FRONTEND_HOST,
            "--server.port",
            FRONTEND_PORT,
        ],
        cwd=ROOT_DIR,
        env=env,
    )

    print(f"Dashboard API: {API_BASE_URL}")
    print(f"Dashboard UI: http://{FRONTEND_HOST}:{FRONTEND_PORT}")
    frontend_process.wait()
    api_process.terminate()


if __name__ == "__main__":
    main()

