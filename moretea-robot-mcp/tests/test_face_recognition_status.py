from __future__ import annotations

from types import SimpleNamespace

from moretea_robot_mcp.face_recognition_status import FaceRecognitionStatusProvider


def test_face_provider_health_is_idle_before_start() -> None:
    provider = FaceRecognitionStatusProvider()

    payload = provider.health()

    assert payload["success"] is True
    assert payload["face_recognition_ready"] is False
    assert payload["snapshot_buffered"] is False
    assert payload["source_topic"] == "/face_recognition/name"


def test_get_recognized_faces_returns_empty_list_without_snapshot() -> None:
    provider = FaceRecognitionStatusProvider()

    payload = provider.get_recognized_faces()

    assert payload == {
        "success": True,
        "faces": [],
        "observed_at": None,
        "source_topic": "/face_recognition/name",
    }


def test_get_recognized_faces_normalizes_json_face_list() -> None:
    provider = FaceRecognitionStatusProvider()
    provider._started = True
    provider._on_message(
        SimpleNamespace(
            data='{"faces":[{"name":"Alice","confidence":0.98},{"name":"Bob"}]}',
            header=SimpleNamespace(stamp=SimpleNamespace(sec=3, nanosec=0)),
        )
    )

    payload = provider.get_recognized_faces()

    assert payload["success"] is True
    assert payload["observed_at"].startswith("1970-01-01T00:00:03")
    assert payload["faces"] == [
        {"name": "Alice", "confidence": 0.98},
        {"name": "Bob", "confidence": None},
    ]


def test_get_recognized_faces_treats_plain_string_as_single_name() -> None:
    provider = FaceRecognitionStatusProvider()
    provider._started = True
    provider._on_message(SimpleNamespace(data="Charlie", header=SimpleNamespace(stamp=None)))

    payload = provider.get_recognized_faces()

    assert payload["success"] is True
    assert payload["faces"] == [{"name": "Charlie", "confidence": None}]
