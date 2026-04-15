from __future__ import annotations

import json
import os
import queue
import threading
import time
import urllib.request
from datetime import datetime, timezone
from typing import Any, Callable
from uuid import uuid4


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class RobotObservabilityReporter:
    def __init__(self) -> None:
        self.enabled = _env_bool("MORETEA_OBSERVABILITY_ENABLED", False)
        self.base_url = os.getenv("MORETEA_OBSERVABILITY_BASE_URL", "http://127.0.0.1:4173").rstrip("/")
        self.machine_id = os.getenv("MORETEA_OBSERVABILITY_MACHINE_ID", "robot-pc")
        self.interval_s = float(os.getenv("MORETEA_OBSERVABILITY_ROBOT_SNAPSHOT_INTERVAL_S", "2"))
        self._queue: queue.Queue[tuple[str, dict[str, Any]]] = queue.Queue()
        self._sender_thread: threading.Thread | None = None
        self._snapshot_thread: threading.Thread | None = None
        self._stop = threading.Event()

    def start(self, snapshot_fn: Callable[[], dict[str, Any]]) -> None:
        if not self.enabled or self._sender_thread is not None:
            return
        self._sender_thread = threading.Thread(target=self._sender_loop, daemon=True, name="moretea_obs_send")
        self._sender_thread.start()
        self._snapshot_thread = threading.Thread(
            target=self._snapshot_loop,
            args=(snapshot_fn,),
            daemon=True,
            name="moretea_obs_robot_snapshot",
        )
        self._snapshot_thread.start()

    def stop(self) -> None:
        self._stop.set()

    def emit_event(self, event: dict[str, Any]) -> None:
        if not self.enabled:
            return
        payload = {"events": [event]}
        self._queue.put(("/api/ingest/events", payload))

    def emit_heartbeat(
        self,
        *,
        machine: dict[str, Any],
        services: list[dict[str, Any]],
        links: list[dict[str, Any]] | None = None,
    ) -> None:
        if not self.enabled:
            return
        self._queue.put(
            (
                "/api/ingest/heartbeats",
                {
                    "machine": machine,
                    "services": services,
                    "links": links or [],
                },
            )
        )

    def next_tool_execution_id(self, tool_name: str) -> str:
        return f"{tool_name}-{uuid4()}"

    def _sender_loop(self) -> None:
        while not self._stop.is_set():
            try:
                path, payload = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                self._post_json(path, payload)
            except Exception:
                continue

    def _snapshot_loop(self, snapshot_fn: Callable[[], dict[str, Any]]) -> None:
        while not self._stop.is_set():
            snapshot = snapshot_fn()
            machine_health = snapshot.get("machine_health", "healthy")
            self.emit_heartbeat(
                machine={
                    "id": self.machine_id,
                    "name": "Robot PC",
                    "summary": "Embodied runtime and ROS2",
                    "health": machine_health,
                },
                services=snapshot.get("services", []),
                links=[],
            )
            self.emit_event(
                {
                    "id": f"robot-snapshot-{uuid4()}",
                    "turn_id": snapshot.get("turn_id"),
                    "machine_id": self.machine_id,
                    "service_id": "robot-control",
                    "type": "robot_snapshot",
                    "status": "healthy" if machine_health == "healthy" else "warning",
                    "timestamp": _utc_now(),
                    "payload_summary": snapshot.get("summary", "Robot snapshot updated."),
                    "raw": {
                        "robot_readiness": snapshot.get("robot_readiness"),
                        "robot_action_state": snapshot.get("robot_action_state"),
                        "personalization": snapshot.get("personalization"),
                    },
                }
            )
            time.sleep(self.interval_s)

    def _post_json(self, path: str, payload: dict[str, Any]) -> None:
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=2.0):
            return
