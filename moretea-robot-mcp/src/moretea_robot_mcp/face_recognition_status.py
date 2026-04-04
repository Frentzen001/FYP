from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

try:
    import rclpy
    import rclpy.executors
    from rclpy.node import Node

    ROS2_AVAILABLE = True
except ImportError:
    ROS2_AVAILABLE = False
    rclpy = None  # type: ignore[assignment]
    Node = object  # type: ignore[assignment,misc]

try:
    from std_msgs.msg import String

    STD_MSGS_AVAILABLE = True
except ImportError:
    STD_MSGS_AVAILABLE = False
    String = object  # type: ignore[assignment,misc]


FACE_RECOGNITION_TOPIC = "/face_recognition/name"


@dataclass(frozen=True)
class FaceSnapshot:
    faces: tuple[dict[str, object], ...]
    observed_at: str


class FaceRecognitionStatusProvider:
    def __init__(self, topic: str = FACE_RECOGNITION_TOPIC) -> None:
        self._topic = topic
        self._node: Any = None
        self._executor: Any = None
        self._spin_thread: threading.Thread | None = None
        self._started = False
        self._startup_error: str | None = None
        self._lock = threading.Lock()
        self._latest_snapshot: FaceSnapshot | None = None

    def start(self) -> None:
        if not ROS2_AVAILABLE:
            self._startup_error = (
                "ROS 2 Python dependencies are unavailable. Source the ROS 2 Humble environment before starting the server."
            )
            raise RuntimeError(self._startup_error)
        if not STD_MSGS_AVAILABLE:
            self._startup_error = "std_msgs is unavailable. Install the ROS standard message packages for face-recognition topics."
            raise RuntimeError(self._startup_error)
        if self._started:
            return

        self._startup_error = None
        self._started = True

        if not rclpy.ok():
            rclpy.init()

        self._node = Node("moretea_face_recognition_status")
        self._node.create_subscription(String, self._topic, self._on_message, 10)

        self._executor = rclpy.executors.MultiThreadedExecutor()
        self._executor.add_node(self._node)
        self._spin_thread = threading.Thread(
            target=self._executor.spin,
            daemon=True,
            name="moretea_face_recognition_spin",
        )
        self._spin_thread.start()

    def shutdown(self) -> None:
        if not self._started:
            return

        try:
            if self._executor:
                try:
                    self._executor.shutdown(wait=False)
                except TypeError:
                    self._executor.shutdown()
            if self._spin_thread is not None:
                self._spin_thread.join(timeout=2.0)
            if self._node:
                self._node.destroy_node()
        finally:
            with self._lock:
                self._latest_snapshot = None
            self._started = False
            self._node = None
            self._executor = None
            self._spin_thread = None

    def health(self) -> dict[str, object]:
        with self._lock:
            latest_snapshot = self._latest_snapshot
        return {
            "success": True,
            "ros_ready": bool(ROS2_AVAILABLE and self._started),
            "face_recognition_ready": bool(self._started and STD_MSGS_AVAILABLE),
            "source_topic": self._topic,
            "snapshot_buffered": latest_snapshot is not None,
            "last_observed_at": None if latest_snapshot is None else latest_snapshot.observed_at,
            "startup_error": self._startup_error,
        }

    def get_recognized_faces(self) -> dict[str, object]:
        with self._lock:
            latest_snapshot = self._latest_snapshot
        if latest_snapshot is None:
            return {
                "success": True,
                "faces": [],
                "observed_at": None,
                "source_topic": self._topic,
            }
        return {
            "success": True,
            "faces": [dict(face) for face in latest_snapshot.faces],
            "observed_at": latest_snapshot.observed_at,
            "source_topic": self._topic,
        }

    def _on_message(self, msg: Any) -> None:
        payload = getattr(msg, "data", "")
        faces = tuple(self._normalize_faces(payload))
        observed_at = self._timestamp_for_message(msg)
        with self._lock:
            self._latest_snapshot = FaceSnapshot(faces=faces, observed_at=observed_at)

    def _normalize_faces(self, payload: Any) -> list[dict[str, object]]:
        if payload is None:
            return []
        if isinstance(payload, str):
            text = payload.strip()
            if not text:
                return []
            try:
                decoded = json.loads(text)
            except json.JSONDecodeError:
                return [{"name": text, "confidence": None}]
            return self._normalize_faces(decoded)
        if isinstance(payload, dict):
            if "faces" in payload:
                return self._normalize_faces(payload["faces"])
            face = {
                "name": str(payload.get("name", "")).strip(),
                "confidence": self._coerce_confidence(payload.get("confidence")),
            }
            if not face["name"]:
                return []
            return [face]
        if isinstance(payload, list):
            normalized: list[dict[str, object]] = []
            for item in payload:
                normalized.extend(self._normalize_faces(item))
            return normalized
        return [{"name": str(payload).strip(), "confidence": None}] if str(payload).strip() else []

    def _coerce_confidence(self, value: object) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _timestamp_for_message(self, msg: Any) -> str:
        stamp = getattr(getattr(msg, "header", None), "stamp", None)
        sec = getattr(stamp, "sec", None)
        nanosec = getattr(stamp, "nanosec", None)
        if isinstance(sec, int) and isinstance(nanosec, int):
            return datetime.fromtimestamp(sec + (nanosec / 1_000_000_000), tz=timezone.utc).isoformat()
        return datetime.now(tz=timezone.utc).isoformat()
