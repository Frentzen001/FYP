from __future__ import annotations

import base64
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

from moretea_robot_mcp.camera_capture import CameraCaptureProvider


def test_camera_provider_health_is_idle_before_start() -> None:
    provider = CameraCaptureProvider()

    payload = provider.health()

    assert payload["success"] is True
    assert payload["camera_ready"] is False
    assert payload["frame_buffered"] is False
    assert payload["source_topic"] == "/camera/image_raw"


def test_capture_image_raises_when_no_frame_is_buffered() -> None:
    provider = CameraCaptureProvider()

    try:
        provider.capture_image()
    except RuntimeError as exc:
        assert "No camera frame is buffered yet" in str(exc)
    else:
        raise AssertionError("capture_image() should fail when no frame is buffered.")


def test_capture_image_returns_base64_jpeg_for_raw_rgb_frame() -> None:
    provider = CameraCaptureProvider()
    message = SimpleNamespace(
        encoding="rgb8",
        width=1,
        height=1,
        data=bytes([255, 0, 0]),
        header=SimpleNamespace(stamp=SimpleNamespace(sec=1, nanosec=0)),
    )

    with patch("moretea_robot_mcp.camera_capture.ROS2_AVAILABLE", True), patch(
        "moretea_robot_mcp.camera_capture.SENSOR_MSGS_AVAILABLE", True
    ):
        provider._started = True
        provider._on_message(message)

    payload = provider.capture_image()
    decoded = base64.b64decode(payload["image_base64"])
    image = Image.open(__import__("io").BytesIO(decoded))

    assert payload["success"] is True
    assert payload["mime_type"] == "image/jpeg"
    assert payload["width"] == 1
    assert payload["height"] == 1
    assert payload["encoding"] == "rgb8"
    assert payload["source_topic"] == "/camera/image_raw"
    assert payload["captured_at"].startswith("1970-01-01T00:00:01")
    assert image.size == (1, 1)


def test_camera_provider_health_exposes_buffered_frame_after_message() -> None:
    provider = CameraCaptureProvider(topic_kind="compressed")
    payload = SimpleNamespace(
        data=base64.b64decode(
            "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsL"
            "DBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAx"
            "NDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIyMjIyMjIy"
            "MjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAARCAA"
            "BAAEDASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAb/xAAeEAACAgEFA"
            "AAAAAAAAAAAAAABAgMRAAQSITEFQf/EABQBAQAAAAAAAAAAAAAAAAAAAAT/xAAX"
            "EQEBAQEAAAAAAAAAAAAAAAABAgAD/9oADAMBAAIRAxEAPwCxrW0qLdwK5aFbWJwB"
            "0R1ya5wqV3lF//2Q=="
        ),
        format="jpeg",
        header=SimpleNamespace(stamp=SimpleNamespace(sec=2, nanosec=0)),
    )

    with patch("moretea_robot_mcp.camera_capture.ROS2_AVAILABLE", True), patch(
        "moretea_robot_mcp.camera_capture.SENSOR_MSGS_AVAILABLE", True
    ):
        provider._started = True
        provider._on_message(payload)
        health = provider.health()

        assert health["camera_ready"] is True
        assert health["frame_buffered"] is True
        assert health["topic_kind"] == "compressed"
        assert health["last_captured_at"].startswith("1970-01-01T00:00:02")
