from __future__ import annotations

import pickle
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from moretea_robot_mcp.face_registration import FaceRegistrationProvider


def test_face_registration_health_is_idle_before_start(tmp_path: Path) -> None:
    provider = FaceRegistrationProvider(db_path=str(tmp_path / "face_db.pkl"))

    payload = provider.health()

    assert payload["success"] is True
    assert payload["face_registration_ready"] is False
    assert payload["service_name"] == "register_face"


def test_register_face_rejects_empty_name(tmp_path: Path) -> None:
    provider = FaceRegistrationProvider(db_path=str(tmp_path / "face_db.pkl"))

    try:
        provider.register_face("   ")
    except ValueError as exc:
        assert str(exc) == "Name must not be empty."
    else:
        raise AssertionError("Empty names should be rejected.")


def test_register_face_rejects_duplicate_name(tmp_path: Path) -> None:
    db_path = tmp_path / "face_db.pkl"
    db_path.write_bytes(pickle.dumps({"Alice": object()}))
    provider = FaceRegistrationProvider(db_path=str(db_path))

    try:
        provider.register_face("Alice")
    except ValueError as exc:
        assert "already registered" in str(exc)
    else:
        raise AssertionError("Duplicate names should be rejected.")


def test_register_face_returns_structured_success_payload(tmp_path: Path) -> None:
    provider = FaceRegistrationProvider(db_path=str(tmp_path / "face_db.pkl"))
    provider._started = True

    class FakeFuture:
        def done(self) -> bool:
            return True

        def result(self) -> object:
            return SimpleNamespace(success=True, message="Ready to register 'Alice' from next visible face")

    class FakeClient:
        def service_is_ready(self) -> bool:
            return True

        def call_async(self, request: object) -> object:
            assert request.name == "Alice"
            return FakeFuture()

    provider._client = FakeClient()
    provider._node = object()

    with patch("moretea_robot_mcp.face_registration.rclpy") as fake_rclpy, patch(
        "moretea_robot_mcp.face_registration.RegisterFace"
    ) as fake_service:
        fake_service.Request.return_value = SimpleNamespace(name="")
        payload = provider.register_face(" Alice ")

    assert payload == {
        "success": True,
        "name": "Alice",
        "message": "Ready to register 'Alice' from next visible face",
        "service_name": "register_face",
        "duplicate": False,
        "db_path": str(tmp_path / "face_db.pkl"),
    }
    fake_rclpy.spin_until_future_complete.assert_called_once()


def test_register_face_reports_service_unavailability(tmp_path: Path) -> None:
    provider = FaceRegistrationProvider(db_path=str(tmp_path / "face_db.pkl"))
    provider._started = True
    provider._client = SimpleNamespace(service_is_ready=lambda: False)

    try:
        provider.register_face("Alice")
    except RuntimeError as exc:
        assert "is not available" in str(exc)
    else:
        raise AssertionError("Service unavailability should raise RuntimeError.")
