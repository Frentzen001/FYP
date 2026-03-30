from __future__ import annotations

import os
import pickle
import threading
from pathlib import Path
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
    from face_tracking_interfaces.srv import RegisterFace

    FACE_REGISTRATION_SERVICE_AVAILABLE = True
except ImportError:
    FACE_REGISTRATION_SERVICE_AVAILABLE = False
    RegisterFace = object  # type: ignore[assignment,misc]


FACE_REGISTRATION_SERVICE = "register_face"
FACE_DB_PATH = "~/.ros/face_db.pkl"


class FaceRegistrationProvider:
    def __init__(
        self,
        service_name: str = FACE_REGISTRATION_SERVICE,
        db_path: str = FACE_DB_PATH,
    ) -> None:
        self._service_name = service_name
        self._db_path = Path(db_path).expanduser()
        self._node: Any = None
        self._executor: Any = None
        self._spin_thread: threading.Thread | None = None
        self._client: Any = None
        self._started = False
        self._startup_error: str | None = None

    def start(self) -> None:
        if not ROS2_AVAILABLE:
            self._startup_error = (
                "ROS 2 Python dependencies are unavailable. Source the ROS 2 Humble environment before starting the server."
            )
            raise RuntimeError(self._startup_error)
        if not FACE_REGISTRATION_SERVICE_AVAILABLE:
            self._startup_error = (
                "face_tracking_interfaces.srv.RegisterFace is unavailable. Install the face registration service package on the robot runtime."
            )
            raise RuntimeError(self._startup_error)
        if self._started:
            return

        self._startup_error = None
        self._started = True

        if not rclpy.ok():
            rclpy.init()

        self._node = Node("moretea_face_registration")
        self._client = self._node.create_client(RegisterFace, self._service_name)
        self._executor = rclpy.executors.MultiThreadedExecutor()
        self._executor.add_node(self._node)
        self._spin_thread = threading.Thread(
            target=self._executor.spin,
            daemon=True,
            name="moretea_face_registration_spin",
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
            if self._node:
                self._node.destroy_node()
        finally:
            if self._spin_thread is not None:
                self._spin_thread.join(timeout=0.5)
            self._started = False
            self._node = None
            self._executor = None
            self._spin_thread = None
            self._client = None

    def health(self) -> dict[str, object]:
        service_ready = bool(self._started and self._client and self._client.service_is_ready())
        return {
            "success": True,
            "ros_ready": bool(ROS2_AVAILABLE and self._started),
            "face_registration_ready": service_ready,
            "service_name": self._service_name,
            "db_path": str(self._db_path),
            "startup_error": self._startup_error,
        }

    def register_face(self, name: str) -> dict[str, object]:
        normalized_name = name.strip()
        if not normalized_name:
            raise ValueError("Name must not be empty.")
        if self._name_exists(normalized_name):
            raise ValueError(f"Face '{normalized_name}' is already registered.")
        if not self._started or self._client is None:
            raise RuntimeError("Face registration provider is not started.")
        if not self._client.service_is_ready():
            raise RuntimeError(f"Face registration service '{self._service_name}' is not available.")

        request = RegisterFace.Request()
        request.name = normalized_name
        future = self._client.call_async(request)
        rclpy.spin_until_future_complete(self._node, future, timeout_sec=5.0)
        if not future.done():
            raise RuntimeError(f"Timed out waiting for face registration service '{self._service_name}'.")

        response = future.result()
        if response is None:
            raise RuntimeError(f"Face registration service '{self._service_name}' returned no response.")

        return {
            "success": bool(getattr(response, "success", False)),
            "name": normalized_name,
            "message": str(getattr(response, "message", "")),
            "service_name": self._service_name,
            "duplicate": False,
            "db_path": str(self._db_path),
        }

    def _name_exists(self, name: str) -> bool:
        if not self._db_path.exists():
            return False
        with self._db_path.open("rb") as handle:
            payload = pickle.load(handle)
        return isinstance(payload, dict) and name in payload
