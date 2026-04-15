from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _env(name: str, default: str) -> str:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip() or default


def _post_json(url: str, payload: dict[str, Any]) -> None:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=2.5):
        return


def _probe_url(url: str) -> tuple[str, str]:
    try:
        request = urllib.request.Request(url, headers={"Accept": "text/event-stream"})
        with urllib.request.urlopen(request, timeout=2.5) as response:
            status = getattr(response, "status", 200)
            if 200 <= status < 500:
                return ("healthy", f"Endpoint reachable with HTTP {status}.")
    except Exception as exc:
        return ("error", str(exc))
    return ("warning", "Probe completed with an unknown result.")


def _docker_running(container_name: str) -> tuple[str, str]:
    try:
        result = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Running}}", container_name],
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return ("warning", "docker CLI is unavailable on this machine.")
    if result.returncode != 0:
        stderr = result.stderr.strip() or result.stdout.strip() or "docker inspect failed"
        return ("error", stderr)
    output = result.stdout.strip().lower()
    if output == "true":
        return ("healthy", f"Container `{container_name}` is running.")
    return ("error", f"Container `{container_name}` is not running.")


def main() -> None:
    base_url = _env("MORETEA_OBSERVABILITY_BASE_URL", "http://127.0.0.1:4173")
    ingest_url = f"{base_url}/api/ingest/heartbeats"
    machine_id = _env("MORETEA_OBSERVABILITY_MACHINE_ID", "openclaw-pc")
    machine_name = _env("MORETEA_OBSERVABILITY_MACHINE_NAME", "OpenClaw PC")
    docker_container = _env("MORETEA_OPENCLAW_CONTAINER_NAME", "moretea-openclaw")
    tunnel_probe_url = _env("MORETEA_OPENCLAW_TUNNEL_PROBE_URL", "http://127.0.0.1:8765/mcp")
    interval_s = float(_env("MORETEA_OPENCLAW_REPORT_INTERVAL_S", "5"))

    while True:
        docker_status, docker_detail = _docker_running(docker_container)
        tunnel_status, tunnel_detail = _probe_url(tunnel_probe_url)
        machine_health = "healthy"
        if "error" in {docker_status, tunnel_status}:
            machine_health = "warning"
        payload = {
            "machine": {
                "id": machine_id,
                "name": machine_name,
                "summary": "Reasoning core and robot tunnel",
                "health": machine_health,
            },
            "services": [
                {
                    "id": "openclaw",
                    "machine_id": machine_id,
                    "name": "OpenClaw Docker",
                    "status": docker_status,
                    "last_heartbeat": _utc_now(),
                    "detail": docker_detail,
                },
                {
                    "id": "ssh-tunnel",
                    "machine_id": machine_id,
                    "name": "SSH tunnel",
                    "status": tunnel_status,
                    "last_heartbeat": _utc_now(),
                    "detail": tunnel_detail,
                },
            ],
            "links": [
                {
                    "id": "openclaw-robot",
                    "source_id": machine_id,
                    "target_id": "robot-pc",
                    "status": tunnel_status,
                    "name": "OpenClaw -> Robot MCP/tunnel",
                    "detail": tunnel_detail,
                    "last_heartbeat": _utc_now(),
                }
            ],
        }
        try:
            _post_json(ingest_url, payload)
        except (urllib.error.URLError, TimeoutError):
            pass
        time.sleep(interval_s)


if __name__ == "__main__":
    main()
