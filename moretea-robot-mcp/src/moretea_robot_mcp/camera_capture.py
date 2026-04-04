from __future__ import annotations

import base64
import io
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import numpy as np
from PIL import Image

try:
    import rclpy
    import rclpy.executors
    from rclpy.node import Node
    from rclpy.qos import QoSPresetProfiles

    ROS2_AVAILABLE = True
except ImportError:
    ROS2_AVAILABLE = False
    rclpy = None  # type: ignore[assignment]
    Node = object  # type: ignore[assignment,misc]
    QoSPresetProfiles = None  # type: ignore[assignment,misc]

try:
    from sensor_msgs.msg import CompressedImage, Image as SensorImage

    SENSOR_MSGS_AVAILABLE = True
except ImportError:
    SENSOR_MSGS_AVAILABLE = False
    CompressedImage = object  # type: ignore[assignment,misc]
    SensorImage = object  # type: ignore[assignment,misc]


CAMERA_TOPIC = "/face_camera/image_raw"
CAMERA_TOPIC_KIND = "raw"
SUPPORTED_CAMERA_TOPIC_KINDS = frozenset({"raw", "compressed"})
_RAW_ENCODINGS = frozenset({"rgb8", "bgr8", "rgba8", "bgra8", "mono8"})


@dataclass(frozen=True)
class BufferedFrame:
    jpeg_bytes: bytes
    width: int
    height: int
    encoding: str
    captured_at: str


class CameraCaptureProvider:
    def __init__(
        self,
        image_topic: str = CAMERA_TOPIC,
        topic_kind: str = CAMERA_TOPIC_KIND,
    ) -> None:
        self._image_topic = image_topic
        self._topic_kind = topic_kind.strip().lower()
        self._node: Any = None
        self._executor: Any = None
        self._spin_thread: threading.Thread | None = None
        self._started = False
        self._startup_error: str | None = None
        self._lock = threading.Lock()
        self._latest_frame: BufferedFrame | None = None

    def start(self) -> None:
        if not ROS2_AVAILABLE:
            self._startup_error = (
                "ROS 2 Python dependencies are unavailable. Source the ROS 2 Humble environment before starting the server."
            )
            raise RuntimeError(self._startup_error)
        if not SENSOR_MSGS_AVAILABLE:
            self._startup_error = "sensor_msgs is unavailable. Install the ROS message packages for camera topics."
            raise RuntimeError(self._startup_error)
        if self._started:
            return
        if self._topic_kind not in SUPPORTED_CAMERA_TOPIC_KINDS:
            self._startup_error = (
                f"Unsupported camera topic kind '{self._topic_kind}'. "
                f"Choose one of: {', '.join(sorted(SUPPORTED_CAMERA_TOPIC_KINDS))}."
            )
            raise RuntimeError(self._startup_error)

        self._startup_error = None
        self._started = True

        if not rclpy.ok():
            rclpy.init()

        self._node = Node("moretea_camera_capture")
        message_type = SensorImage if self._topic_kind == "raw" else CompressedImage
        qos = QoSPresetProfiles.SENSOR_DATA.value
        self._node.create_subscription(message_type, self._image_topic, self._on_message, qos)

        self._executor = rclpy.executors.MultiThreadedExecutor()
        self._executor.add_node(self._node)
        self._spin_thread = threading.Thread(
            target=self._executor.spin,
            daemon=True,
            name="moretea_camera_capture_spin",
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
                self._latest_frame = None
            self._started = False
            self._node = None
            self._executor = None
            self._spin_thread = None

    def health(self) -> dict[str, object]:
        with self._lock:
            latest_frame = self._latest_frame
        return {
            "success": True,
            "ros_ready": bool(ROS2_AVAILABLE and self._started),
            "camera_ready": bool(self._started and SENSOR_MSGS_AVAILABLE),
            "source_topic": self._image_topic,
            "topic_kind": self._topic_kind,
            "frame_buffered": latest_frame is not None,
            "last_captured_at": None if latest_frame is None else latest_frame.captured_at,
            "startup_error": self._startup_error,
        }

    def capture_image(self) -> dict[str, object]:
        with self._lock:
            latest_frame = self._latest_frame
        if latest_frame is None:
            raise RuntimeError(
                f"No camera frame is buffered yet from topic '{self._image_topic}'."
            )
        return {
            "success": True,
            "image_base64": base64.b64encode(latest_frame.jpeg_bytes).decode("ascii"),
            "mime_type": "image/jpeg",
            "width": latest_frame.width,
            "height": latest_frame.height,
            "encoding": latest_frame.encoding,
            "captured_at": latest_frame.captured_at,
            "source_topic": self._image_topic,
        }

    def _on_message(self, msg: Any) -> None:
        frame = self._buffer_frame(msg)
        with self._lock:
            self._latest_frame = frame

    def _buffer_frame(self, msg: Any) -> BufferedFrame:
        if self._topic_kind == "compressed":
            return self._buffer_compressed(msg)
        return self._buffer_raw(msg)

    def _buffer_compressed(self, msg: Any) -> BufferedFrame:
        payload = bytes(getattr(msg, "data", b""))
        if not payload:
            raise RuntimeError("Compressed camera message does not contain image bytes.")
        image = Image.open(io.BytesIO(payload))
        width, height = image.size
        return BufferedFrame(
            jpeg_bytes=payload,
            width=width,
            height=height,
            encoding="jpeg",
            captured_at=self._timestamp_for_message(msg),
        )

    def _buffer_raw(self, msg: Any) -> BufferedFrame:
        encoding = str(getattr(msg, "encoding", "")).strip().lower()
        if encoding not in _RAW_ENCODINGS:
            raise RuntimeError(
                f"Unsupported raw camera encoding '{encoding}'. Supported encodings: {', '.join(sorted(_RAW_ENCODINGS))}."
            )
        width = int(getattr(msg, "width", 0))
        height = int(getattr(msg, "height", 0))
        if width <= 0 or height <= 0:
            raise RuntimeError("Raw camera message is missing valid width/height metadata.")

        pixel_data = np.frombuffer(bytes(getattr(msg, "data", b"")), dtype=np.uint8)
        expected_channels = 1 if encoding == "mono8" else (4 if "a8" in encoding else 3)
        expected_size = width * height * expected_channels
        if pixel_data.size != expected_size:
            raise RuntimeError(
                f"Raw camera payload size mismatch: expected {expected_size} bytes, received {pixel_data.size}."
            )

        array = pixel_data.reshape((height, width, expected_channels))
        if encoding == "bgr8":
            array = array[:, :, ::-1]
            image_mode = "RGB"
        elif encoding == "bgra8":
            array = array[:, :, [2, 1, 0, 3]]
            image_mode = "RGBA"
        elif encoding == "rgba8":
            image_mode = "RGBA"
        elif encoding == "mono8":
            array = pixel_data.reshape((height, width))
            image_mode = "L"
        else:
            image_mode = "RGB"

        image = Image.fromarray(array, mode=image_mode)
        if image_mode == "RGBA":
            image = image.convert("RGB")
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=85)
        return BufferedFrame(
            jpeg_bytes=buffer.getvalue(),
            width=width,
            height=height,
            encoding=encoding,
            captured_at=self._timestamp_for_message(msg),
        )

    def _timestamp_for_message(self, msg: Any) -> str:
        stamp = getattr(getattr(msg, "header", None), "stamp", None)
        sec = getattr(stamp, "sec", None)
        nanosec = getattr(stamp, "nanosec", None)
        if isinstance(sec, int) and isinstance(nanosec, int):
            return datetime.fromtimestamp(sec + (nanosec / 1_000_000_000), tz=timezone.utc).isoformat()
        return datetime.now(tz=timezone.utc).isoformat()
