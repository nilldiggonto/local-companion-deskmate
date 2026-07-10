import subprocess
import sys
import time

import httpx

HEALTH_URL = "http://127.0.0.1:8000/health"


def start_server() -> subprocess.Popen:
    process = subprocess.Popen([sys.executable, "-m", "uvicorn", "server.main:app"])
    _wait_until_ready()
    return process


def _wait_until_ready(timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            httpx.get(HEALTH_URL, timeout=1.0)
            return
        except httpx.HTTPError:
            time.sleep(0.3)
