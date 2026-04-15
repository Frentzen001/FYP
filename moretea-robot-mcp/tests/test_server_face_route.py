from __future__ import annotations

from unittest.mock import patch

import pytest
from starlette.testclient import TestClient

from moretea_robot_mcp.server import build_streamable_http_app


def _make_face(name: str) -> dict:
    return {"name": name, "confidence": None}


def _make_ctx(faces: list[dict]):
    """Return a minimal fake AppContext whose face_recognition returns the given faces."""

    class FakeFaceRecognition:
        def get_recognized_faces(self) -> dict:
            return {"success": True, "faces": faces}

    class FakeCtx:
        face_recognition = FakeFaceRecognition()

    return FakeCtx()


@pytest.fixture()
def client():
    app = build_streamable_http_app()
    return TestClient(app, raise_server_exceptions=True)


def test_face_route_returns_name_when_face_recognized(client: TestClient) -> None:
    ctx = _make_ctx([_make_face("Frentzen")])
    with patch("moretea_robot_mcp.server._ctx_singleton", ctx):
        resp = client.get("/face")
    assert resp.status_code == 200
    assert resp.json() == {"name": "Frentzen"}


def test_face_route_returns_unknown_when_topic_says_unknown(client: TestClient) -> None:
    ctx = _make_ctx([_make_face("Unknown")])
    with patch("moretea_robot_mcp.server._ctx_singleton", ctx):
        resp = client.get("/face")
    assert resp.status_code == 200
    assert resp.json() == {"name": "Unknown"}


def test_face_route_returns_null_when_no_faces(client: TestClient) -> None:
    ctx = _make_ctx([])
    with patch("moretea_robot_mcp.server._ctx_singleton", ctx):
        resp = client.get("/face")
    assert resp.status_code == 200
    assert resp.json() == {"name": None}


def test_face_route_returns_null_when_singleton_not_initialized(client: TestClient) -> None:
    with patch("moretea_robot_mcp.server._ctx_singleton", None):
        resp = client.get("/face")
    assert resp.status_code == 200
    assert resp.json() == {"name": None}


def test_face_route_returns_null_when_name_is_empty_string(client: TestClient) -> None:
    ctx = _make_ctx([_make_face("")])
    with patch("moretea_robot_mcp.server._ctx_singleton", ctx):
        resp = client.get("/face")
    assert resp.status_code == 200
    assert resp.json() == {"name": None}
