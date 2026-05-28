"""Run the dashboard FastAPI server and Streamlit UI together."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

ROOT_DIR = Path(__file__).resolve().parents[2]
ROOT_DIR_STR = str(ROOT_DIR)
if ROOT_DIR_STR not in sys.path:
    sys.path.insert(0, ROOT_DIR_STR)

from dotenv import load_dotenv

from src.common.observability.langsmith import configure_langsmith

# Load environment variables before spawning child processes so they inherit DB and tracing config.
load_dotenv()
configure_langsmith("dashboard")

API_HOST = os.environ.get("DASHBOARD_API_HOST", "127.0.0.1")
FRONTEND_HOST = os.environ.get("DASHBOARD_FRONTEND_HOST", "127.0.0.1")


def configure_runtime_env(env: dict[str, str]) -> dict[str, str]:
    """Normalize optional tracing settings before starting child processes."""

    if not env.get("LANGSMITH_API_KEY", "").strip() and not env.get("LANGCHAIN_API_KEY", "").strip():
        env["LANGSMITH_TRACING"] = "false"
        env["LANGCHAIN_TRACING_V2"] = "false"
    return env


def resolve_port(host: str, preferred_port: int) -> int:
    """Use the preferred port when free, otherwise fall back to the next free port."""

    for port in range(preferred_port, preferred_port + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if sock.connect_ex((host, port)) != 0:
                return port
    raise RuntimeError(f"no available port found near {host}:{preferred_port}")


def wait_for_http_ready(name: str, url: str, process: subprocess.Popen[str] | subprocess.Popen[bytes]) -> None:
    """Wait until a local HTTP server responds, or fail fast if the child exits."""

    for _ in range(30):
        if process.poll() is not None:
            raise RuntimeError(f"{name} exited before becoming ready")
        try:
            with urlopen(url, timeout=1) as response:
                if 200 <= response.status < 500:
                    return
        except HTTPError as exc:
            if 200 <= exc.code < 500:
                return
        except OSError:
            time.sleep(1)
    raise RuntimeError(f"{name} did not start: {url}")


def main() -> None:
    api_port = resolve_port(API_HOST, int(os.environ.get("DASHBOARD_API_PORT", "8010")))
    frontend_port = resolve_port(FRONTEND_HOST, int(os.environ.get("DASHBOARD_FRONTEND_PORT", "8510")))
    api_base_url = f"http://{API_HOST}:{api_port}"
    frontend_url = f"http://{FRONTEND_HOST}:{frontend_port}"

    env = configure_runtime_env(os.environ.copy())
    env["DASHBOARD_API_HOST"] = API_HOST
    env["DASHBOARD_API_PORT"] = str(api_port)
    env["DASHBOARD_FRONTEND_HOST"] = FRONTEND_HOST
    env["DASHBOARD_FRONTEND_PORT"] = str(frontend_port)
    env["DASHBOARD_API_BASE_URL"] = api_base_url

    api_process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "src.dashboard.api.main:app",
            "--host",
            API_HOST,
            "--port",
            str(api_port),
        ],
        cwd=ROOT_DIR,
        env=env,
    )
    wait_for_http_ready("dashboard API", f"{api_base_url}/openapi.json", api_process)

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
            str(frontend_port),
        ],
        cwd=ROOT_DIR,
        env=env,
    )
    wait_for_http_ready("dashboard UI", frontend_url, frontend_process)

    print(f"Dashboard API: {api_base_url}")
    print(f"Dashboard UI: {frontend_url}")
    try:
        frontend_process.wait()
    finally:
        api_process.terminate()


if __name__ == "__main__":
    main()
