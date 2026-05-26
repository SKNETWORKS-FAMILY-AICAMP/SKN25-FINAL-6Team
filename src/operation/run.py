"""Run the operation FastAPI server and Streamlit UI together."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import urlopen

ROOT_DIR = Path(__file__).resolve().parents[2]
ROOT_DIR_STR = str(ROOT_DIR)
if ROOT_DIR_STR not in sys.path:
    sys.path.insert(0, ROOT_DIR_STR)

from dotenv import load_dotenv

from src.common.observability.langsmith import configure_langsmith

# .env 로드: os.environ.copy() 전에 실행해야 LangSmith 변수가 서브프로세스 env에 포함된다
load_dotenv()
configure_langsmith("operation")

API_HOST = os.environ.get("OPERATION_API_HOST", "127.0.0.1")
API_PORT = os.environ.get("OPERATION_API_PORT", "8001")
FRONTEND_HOST = os.environ.get("OPERATION_FRONTEND_HOST", "127.0.0.1")
FRONTEND_PORT = os.environ.get("OPERATION_FRONTEND_PORT", "8501")
API_BASE_URL = f"http://{API_HOST}:{API_PORT}"


def wait_for_api() -> None:
    # range(30): uvicorn 콜드 스타트 최대 30초 가정, 1초 간격 폴링 (dashboard/run.py와 동일 기준)
    for _ in range(30):
        try:
            with urlopen(f"{API_BASE_URL}/health", timeout=1) as response:
                if response.status == 200:
                    return
        except OSError:
            time.sleep(1)
    raise RuntimeError(f"operation API did not start: {API_BASE_URL}")


def main() -> None:
    env = os.environ.copy()
    env["OPERATION_API_BASE_URL"] = API_BASE_URL
    # LangSmith 프로젝트를 operation 전용으로 고정해 dashboard 트레이스와 분리한다

    api_process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "src.operation.api.main:app",
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
            "src/operation/frontend/app.py",
            "--server.address",
            FRONTEND_HOST,
            "--server.port",
            FRONTEND_PORT,
        ],
        cwd=ROOT_DIR,
        env=env,
    )

    print(f"Operation API: {API_BASE_URL}")
    print(f"Operation UI: http://{FRONTEND_HOST}:{FRONTEND_PORT}")
    frontend_process.wait()
    api_process.terminate()


if __name__ == "__main__":
    main()
