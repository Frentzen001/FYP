from __future__ import annotations

import queue
import threading
import time
from typing import Any

from .eye_control import (
    EYE_EXPRESSION_TOPIC,
    SUPPORTED_EMOTIONS,
    normalize_emotion_name,
    resolve_emotion_code,
)

try:
    import rclpy
    import rclpy.executors
    from rclpy.node import Node
    from std_msgs.msg import Int32

    ROS2_AVAILABLE = True
except ImportError:
    ROS2_AVAILABLE = False
    rclpy = None  # type: ignore[assignment]
    Node = object  # type: ignore[assignment,misc]
    Int32 = object  # type: ignore[assignment,misc]


class EyeExpressionPublisher:
    _DRAIN_INTERVAL_SEC = 0.01
    _PUBLISH_ACK_TIMEOUT_SEC = 0.5

    def __init__(self, topic: str = EYE_EXPRESSION_TOPIC) -> None:
        self._topic = topic
        self._node: Any = None
        self._executor: Any = None
        self._publisher: Any = None
        self._spin_thread: threading.Thread | None = None
        self._publish_queue: queue.Queue[tuple[int, threading.Event | None]] = queue.Queue()
        self._started = False

    def start(self) -> None:
        if not ROS2_AVAILABLE:
            raise RuntimeError(
                "ROS 2 Python dependencies are unavailable. Source the ROS 2 Humble environment before starting the server."
            )
        if self._started:
            return

        if not rclpy.ok():
            rclpy.init()

        self._node = Node("moretea_eye_control")
        self._publisher = self._node.create_publisher(Int32, self._topic, 10)
        self._node.create_timer(self._DRAIN_INTERVAL_SEC, self._drain_publish_queue)

        self._executor = rclpy.executors.MultiThreadedExecutor()
        self._executor.add_node(self._node)
        self._spin_thread = threading.Thread(
            target=self._executor.spin,
            daemon=True,
            name="moretea_eye_control_spin",
        )
        self._spin_thread.start()
        self._started = True

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
            self._started = False
            self._publisher = None
            self._node = None
            self._executor = None
            self._spin_thread = None

    def health(self) -> dict[str, Any]:
        return {
            "success": True,
            "ros_ready": bool(ROS2_AVAILABLE and self._started),
            "topic": self._topic,
            "supported_emotions": list(SUPPORTED_EMOTIONS),
        }

    def publish_emotion(self, mood: str) -> dict[str, Any]:
        if not self._started:
            raise RuntimeError("EyeExpressionPublisher is not running.")

        normalized = normalize_emotion_name(mood)
        code = resolve_emotion_code(normalized)
        self._publish_and_wait(code)

        return {
            "success": True,
            "mood": normalized,
            "code": code,
            "topic": self._topic,
        }

    def publish_code_once(self, code: int, wait_seconds: float = 0.25) -> None:
        if not self._started:
            raise RuntimeError("EyeExpressionPublisher is not running.")
        self._publish_and_wait(code)
        time.sleep(wait_seconds)

    def _publish_and_wait(self, code: int) -> None:
        published = threading.Event()
        self._publish_queue.put((code, published))
        if not published.wait(timeout=self._PUBLISH_ACK_TIMEOUT_SEC):
            raise RuntimeError(f"Timed out publishing eye expression code {code}.")

    def _drain_publish_queue(self) -> None:
        if not self._publisher:
            return

        while True:
            try:
                code, published = self._publish_queue.get_nowait()
            except queue.Empty:
                return

            msg = Int32()
            msg.data = code
            self._publisher.publish(msg)
            if published is not None:
                published.set()
