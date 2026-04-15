from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import patch

from moretea_robot_mcp import server
from moretea_robot_mcp.tour_stops import TourStop


_REAL_APP_CONTEXT = server.AppContext


class FakePublisher:
    def __init__(self) -> None:
        self.started = False
        self.shutdown_called = False
        self.health_payload = {
            "success": True,
            "ros_ready": False,
            "topic": "/eye_expression",
            "supported_emotions": ["happy", "sad"],
        }
        self.publish_result = {
            "success": True,
            "mood": "happy",
            "code": 1,
            "topic": "/eye_expression",
        }

    def start(self) -> None:
        self.started = True
        self.health_payload["ros_ready"] = True

    def shutdown(self) -> None:
        self.shutdown_called = True

    def health(self) -> dict[str, object]:
        return dict(self.health_payload)

    def publish_emotion(self, mood: str) -> dict[str, object]:
        if isinstance(self.publish_result, Exception):
            raise self.publish_result
        payload = dict(self.publish_result)
        payload["mood"] = mood.strip().lower()
        return payload


class FakeCamera:
    def __init__(self, *_args: object, **_kwargs: object) -> None:
        self.started = False
        self.shutdown_called = False
        self.health_payload = {
            "success": True,
            "ros_ready": False,
            "camera_ready": False,
            "source_topic": "/camera/image_raw",
            "topic_kind": "raw",
            "frame_buffered": False,
            "last_captured_at": None,
            "startup_error": None,
        }
        self.capture_payload = {
            "success": True,
            "image_base64": "ZmFrZS1qcGVn",
            "mime_type": "image/jpeg",
            "width": 640,
            "height": 480,
            "encoding": "rgb8",
            "captured_at": "ts",
            "source_topic": "/camera/image_raw",
        }

    def start(self) -> None:
        self.started = True
        self.health_payload["ros_ready"] = True
        self.health_payload["camera_ready"] = True

    def shutdown(self) -> None:
        self.shutdown_called = True

    def health(self) -> dict[str, object]:
        return dict(self.health_payload)

    def capture_image(self) -> dict[str, object]:
        if isinstance(self.capture_payload, Exception):
            raise self.capture_payload
        return dict(self.capture_payload)


class FakeFaceRecognition:
    def __init__(self, *_args: object, **_kwargs: object) -> None:
        self.started = False
        self.shutdown_called = False
        self.health_payload = {
            "success": True,
            "ros_ready": False,
            "face_recognition_ready": False,
            "source_topic": "/face_recognition/name",
            "snapshot_buffered": False,
            "last_observed_at": None,
            "startup_error": None,
        }
        self.faces_payload = {
            "success": True,
            "faces": [{"name": "Alice", "confidence": 0.97}],
            "observed_at": "ts",
            "source_topic": "/face_recognition/name",
        }

    def start(self) -> None:
        self.started = True
        self.health_payload["ros_ready"] = True
        self.health_payload["face_recognition_ready"] = True

    def shutdown(self) -> None:
        self.shutdown_called = True

    def health(self) -> dict[str, object]:
        return dict(self.health_payload)

    def get_recognized_faces(self) -> dict[str, object]:
        return dict(self.faces_payload)


class FakeFaceRegistration:
    def __init__(self, *_args: object, **_kwargs: object) -> None:
        self.started = False
        self.shutdown_called = False
        self.health_payload = {
            "success": True,
            "ros_ready": False,
            "face_registration_ready": False,
            "service_name": "register_face",
            "db_path": "/tmp/face_db.pkl",
            "startup_error": None,
        }
        self.register_payload = {
            "success": True,
            "name": "Alice",
            "message": "Ready to register 'Alice' from next visible face",
            "service_name": "register_face",
            "duplicate": False,
            "db_path": "/tmp/face_db.pkl",
        }
        self._db_path = "/tmp/face_db.pkl"

    def start(self) -> None:
        self.started = True
        self.health_payload["ros_ready"] = True
        self.health_payload["face_registration_ready"] = True

    def shutdown(self) -> None:
        self.shutdown_called = True

    def health(self) -> dict[str, object]:
        return dict(self.health_payload)

    def register_face(self, name: str) -> dict[str, object]:
        if isinstance(self.register_payload, Exception):
            raise self.register_payload
        payload = dict(self.register_payload)
        payload["name"] = name.strip()
        return payload


class FakeNavigation:
    def __init__(self) -> None:
        self.started = False
        self.shutdown_called = False
        self.health_payload = {
            "success": True,
            "ros_ready": False,
            "nav2_ready": False,
            "status_topic": "/navigate_to_pose/_action/status",
            "feedback_topic": "/navigate_to_pose/_action/feedback",
            "startup_error": None,
        }
        self.status_payload = {
            "success": True,
            "available": False,
            "is_navigating": False,
            "distance_remaining_m": None,
            "recovery_count": 0,
            "replan_count": 0,
            "last_event_note": None,
            "status_text": "Navigation is unavailable.",
        }

    def start(self) -> None:
        self.started = True
        self.health_payload["ros_ready"] = True
        self.health_payload["nav2_ready"] = True

    def shutdown(self) -> None:
        self.shutdown_called = True

    def health(self) -> dict[str, object]:
        return dict(self.health_payload)

    def status(self) -> dict[str, object]:
        if isinstance(self.status_payload, Exception):
            raise self.status_payload
        return dict(self.status_payload)


class FakeTourNavigation:
    def __init__(self) -> None:
        self.started = False
        self.shutdown_called = False
        self.health_payload = {
            "success": True,
            "nav2_ready": False,
            "nav2_import_ready": False,
            "nav2_active_check_bypassed": True,
            "active_goal": False,
            "active_stop_id": None,
            "startup_error": None,
            "readiness_detail": "Nav2 commander has not been initialized.",
        }
        self.status_payload = {
            "success": True,
            "active_goal": False,
            "active_stop_id": None,
            "active_stop_name": None,
            "distance_remaining_m": None,
            "recovery_count": 0,
            "replan_count": 0,
            "last_event_note": None,
            "last_outcome": None,
            "action_id": None,
            "status": "idle",
            "detail": "No navigation action has been started.",
            "created_at": None,
            "started_at": None,
            "completed_at": None,
            "last_updated_at": None,
            "session_id": None,
            "turn_id": None,
        }
        self.start_payload = {
            "success": True,
            "action_id": "action-1",
            "session_id": None,
            "turn_id": None,
            "status": "accepted",
            "stop_id": "entrance",
            "stop_name": "Entrance",
            "distance_remaining_m": None,
            "recovery_count": 0,
            "replan_count": 0,
            "last_event_note": None,
            "detail": "Navigation accepted.",
            "created_at": "ts",
            "started_at": None,
            "completed_at": None,
            "last_updated_at": "ts",
        }
        self.navigate_result = {
            "success": True,
            "action_id": "action-1",
            "stop_id": "entrance",
            "stop_name": "Entrance",
            "outcome": "succeeded",
            "detail": "Reached destination.",
            "distance_remaining_m": None,
            "recovery_count": 0,
            "replan_count": 0,
            "last_event_note": None,
        }

    def start(self) -> None:
        self.started = True
        self.health_payload["nav2_ready"] = True

    def shutdown(self) -> None:
        self.shutdown_called = True

    def health(self) -> dict[str, object]:
        return dict(self.health_payload)

    def current_status(self) -> dict[str, object]:
        return dict(self.status_payload)

    def start_navigation_to_stop(
        self,
        stop: TourStop,
        session_id: str | None = None,
        turn_id: str | None = None,
    ) -> dict[str, object]:
        payload = dict(self.start_payload)
        payload["stop_id"] = stop.id
        payload["stop_name"] = stop.name
        payload["session_id"] = session_id
        payload["turn_id"] = turn_id
        return payload

    def get_navigation_action_status(self, action_id: str) -> dict[str, object]:
        payload = dict(self.start_payload)
        payload["action_id"] = action_id
        payload["status"] = "running"
        return payload

    def navigate_to_stop(self, stop: TourStop) -> dict[str, object]:
        payload = dict(self.navigate_result)
        payload["stop_id"] = stop.id
        payload["stop_name"] = stop.name
        return payload

    def cancel_navigation(self, action_id: str | None = None) -> dict[str, object]:
        return {
            "success": True,
            "action_id": action_id,
            "status": "cancelled",
            "active_goal": False,
            "active_stop_id": None,
            "detail": "No active navigation task to cancel.",
        }


class FakeMotion:
    def __init__(self) -> None:
        self.started = False
        self.shutdown_called = False
        self.health_payload = {
            "success": True,
            "ros_ready": False,
            "topic": "/cmd_vel",
            "max_linear_vel": 0.4,
            "max_angular_vel": 0.8,
            "motion_active": False,
            "startup_error": None,
        }

    def start(self) -> None:
        self.started = True
        self.health_payload["ros_ready"] = True

    def shutdown(self) -> None:
        self.shutdown_called = True

    def health(self) -> dict[str, object]:
        return dict(self.health_payload)

    def move_distance(self, *_args: object, **_kwargs: object) -> dict[str, object]:
        return {"success": True, "requested_distance_m": 1.0, "actual_distance_m": 1.0, "timed_out": False}

    def rotate_angle(self, *_args: object, **_kwargs: object) -> dict[str, object]:
        return {"success": True, "requested_angle_deg": 90.0, "actual_angle_deg": 90.0, "timed_out": False}

    def stop(self) -> dict[str, object]:
        return {"success": True, "detail": "Zero velocity published."}


class FakeSensors:
    def __init__(self) -> None:
        self.started = False
        self.shutdown_called = False
        self.health_payload = {
            "success": True,
            "ros_ready": False,
            "odom_received": True,
            "odom_fresh": True,
            "odom_age_s": 0.1,
            "battery_received": False,
            "scan_received": False,
            "startup_error": None,
        }

    def start(self) -> None:
        self.started = True
        self.health_payload["ros_ready"] = True

    def shutdown(self) -> None:
        self.shutdown_called = True

    def health(self) -> dict[str, object]:
        return dict(self.health_payload)

    def has_fresh_odometry(self) -> bool:
        return True

    def get_position(self) -> tuple[float, float]:
        return (0.0, 0.0)

    def get_yaw(self) -> float:
        return 0.0


class FakeObservability:
    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []

    def emit_event(self, event: dict[str, object]) -> None:
        self.events.append(event)

    def next_tool_execution_id(self, tool_name: str) -> str:
        return f"{tool_name}-test"


def _app_context_factory(**kwargs: object):
    kwargs.setdefault("motion", FakeMotion())
    kwargs.setdefault("sensors", FakeSensors())
    return _REAL_APP_CONTEXT(**kwargs)


server.AppContext = _app_context_factory  # type: ignore[assignment]


def make_ctx(app_context: server.AppContext, *, meta: dict[str, object] | None = None):
    return SimpleNamespace(
        request_context=SimpleNamespace(
            lifespan_context=app_context,
            meta=meta,
            request=None,
            session=SimpleNamespace(client_params=None),
        )
    )


def test_health_reports_nested_provider_statuses() -> None:
    ctx = make_ctx(
        server.AppContext(
            publisher=FakePublisher(),
            camera=FakeCamera(),
            face_recognition=FakeFaceRecognition(),
            face_registration=FakeFaceRegistration(),
            navigation=FakeNavigation(),
            tour_navigation=FakeTourNavigation(),
            tour_stops=(),
        )
    )

    payload = server.health(ctx)

    assert payload["success"] is True
    assert payload["robot_control_ready"] is False
    assert payload["camera_ready"] is False
    assert payload["face_recognition_ready"] is False
    assert payload["face_registration_ready"] is False
    assert payload["navigation_ready"] is False
    assert payload["publisher"]["topic"] == "/eye_expression"
    assert payload["camera"]["source_topic"] == "/camera/image_raw"
    assert payload["face_recognition"]["source_topic"] == "/face_recognition/name"
    assert payload["face_registration"]["service_name"] == "register_face"
    assert payload["navigation"]["status_topic"] == "/navigate_to_pose/_action/status"
    assert payload["tour_navigation"]["active_goal"] is False
    assert payload["tour_navigation"]["nav2_active_check_bypassed"] is True
    assert payload["startup_errors"] == {
        "publisher": None,
        "camera": None,
        "face_recognition": None,
        "face_registration": None,
        "navigation": None,
        "tour_navigation": None,
        "motion": None,
        "sensors": None,
        "tour_stops": None,
    }


def test_express_emotion_returns_structured_error_for_invalid_mood() -> None:
    publisher = FakePublisher()
    publisher.publish_result = ValueError("Unsupported emotion 'curious'.")
    ctx = make_ctx(
        server.AppContext(
            publisher=publisher,
            camera=FakeCamera(),
            face_recognition=FakeFaceRecognition(),
            face_registration=FakeFaceRegistration(),
            navigation=FakeNavigation(),
            tour_navigation=FakeTourNavigation(),
            tour_stops=(),
        )
    )

    payload = server.express_emotion("curious", ctx)

    assert payload == {
        "success": False,
        "error": "Unsupported emotion 'curious'.",
        "mood": "curious",
    }


def test_capture_image_returns_camera_payload() -> None:
    ctx = make_ctx(
        server.AppContext(
            publisher=FakePublisher(),
            camera=FakeCamera(),
            face_recognition=FakeFaceRecognition(),
            face_registration=FakeFaceRegistration(),
            navigation=FakeNavigation(),
            tour_navigation=FakeTourNavigation(),
            tour_stops=(),
        )
    )

    payload = server.capture_image(ctx)

    assert isinstance(payload, list)
    assert len(payload) == 1


def test_capture_image_returns_structured_error_when_no_frame_is_buffered() -> None:
    camera = FakeCamera()
    camera.capture_payload = RuntimeError("No camera frame is buffered yet from topic '/camera/image_raw'.")
    ctx = make_ctx(
        server.AppContext(
            publisher=FakePublisher(),
            camera=camera,
            face_recognition=FakeFaceRecognition(),
            face_registration=FakeFaceRegistration(),
            navigation=FakeNavigation(),
            tour_navigation=FakeTourNavigation(),
            tour_stops=(),
        )
    )

    payload = server.capture_image(ctx)

    assert payload["success"] is False
    assert "No camera frame is buffered yet" in str(payload["error"])


def test_get_recognized_faces_returns_face_snapshot() -> None:
    ctx = make_ctx(
        server.AppContext(
            publisher=FakePublisher(),
            camera=FakeCamera(),
            face_recognition=FakeFaceRecognition(),
            face_registration=FakeFaceRegistration(),
            navigation=FakeNavigation(),
            tour_navigation=FakeTourNavigation(),
            tour_stops=(),
        )
    )

    payload = server.get_recognized_faces(ctx)

    assert payload["success"] is True
    assert payload["faces"] == [{"name": "Alice", "confidence": 0.97}]


def test_get_recognized_faces_allows_empty_results() -> None:
    face_recognition = FakeFaceRecognition()
    face_recognition.faces_payload = {
        "success": True,
        "faces": [],
        "observed_at": "ts",
        "source_topic": "/face_recognition/name",
    }
    ctx = make_ctx(
        server.AppContext(
            publisher=FakePublisher(),
            camera=FakeCamera(),
            face_recognition=face_recognition,
            face_registration=FakeFaceRegistration(),
            navigation=FakeNavigation(),
            tour_navigation=FakeTourNavigation(),
            tour_stops=(),
        )
    )

    payload = server.get_recognized_faces(ctx)

    assert payload["success"] is True
    assert payload["faces"] == []


def test_register_face_returns_provider_payload() -> None:
    ctx = make_ctx(
        server.AppContext(
            publisher=FakePublisher(),
            camera=FakeCamera(),
            face_recognition=FakeFaceRecognition(),
            face_registration=FakeFaceRegistration(),
            navigation=FakeNavigation(),
            tour_navigation=FakeTourNavigation(),
            tour_stops=(),
        )
    )

    payload = server.register_face(" Alice ", ctx)

    assert payload["success"] is True
    assert payload["name"] == "Alice"
    assert payload["duplicate"] is False


def test_register_face_surfaces_duplicate_rejection() -> None:
    face_registration = FakeFaceRegistration()
    face_registration.register_payload = ValueError("Face 'Alice' is already registered.")
    ctx = make_ctx(
        server.AppContext(
            publisher=FakePublisher(),
            camera=FakeCamera(),
            face_recognition=FakeFaceRecognition(),
            face_registration=face_registration,
            navigation=FakeNavigation(),
            tour_navigation=FakeTourNavigation(),
            tour_stops=(),
        )
    )

    payload = server.register_face("Alice", ctx)

    assert payload["success"] is False
    assert payload["name"] == "Alice"
    assert payload["duplicate"] is True


def test_register_face_surfaces_runtime_failure() -> None:
    face_registration = FakeFaceRegistration()
    face_registration.register_payload = RuntimeError("Face registration service 'register_face' is not available.")
    ctx = make_ctx(
        server.AppContext(
            publisher=FakePublisher(),
            camera=FakeCamera(),
            face_recognition=FakeFaceRecognition(),
            face_registration=face_registration,
            navigation=FakeNavigation(),
            tour_navigation=FakeTourNavigation(),
            tour_stops=(),
        )
    )

    payload = server.register_face("Alice", ctx)

    assert payload["success"] is False
    assert payload["duplicate"] is False


def test_get_navigation_status_returns_provider_payload() -> None:
    navigation = FakeNavigation()
    navigation.status_payload = {
        "success": True,
        "available": True,
        "is_navigating": True,
        "distance_remaining_m": 1.5,
        "recovery_count": 1,
        "replan_count": 0,
        "last_event_note": "I am taking a moment to recover around an obstacle.",
        "status_text": "Approximately 1.5 metres remain.",
    }
    ctx = make_ctx(
        server.AppContext(
            publisher=FakePublisher(),
            camera=FakeCamera(),
            face_recognition=FakeFaceRecognition(),
            face_registration=FakeFaceRegistration(),
            navigation=navigation,
            tour_navigation=FakeTourNavigation(),
            tour_stops=(),
        )
    )

    payload = server.get_navigation_status(ctx)

    assert payload["success"] is True
    assert payload["is_navigating"] is True
    assert payload["distance_remaining_m"] == 1.5


def test_navigate_to_stop_returns_terminal_payload() -> None:
    stops = (
        TourStop("entrance", "Entrance", ("front door",), 0.0, 0.0, 1.0, "Start here."),
    )
    ctx = make_ctx(
        server.AppContext(
            publisher=FakePublisher(),
            camera=FakeCamera(),
            face_recognition=FakeFaceRecognition(),
            face_registration=FakeFaceRegistration(),
            navigation=FakeNavigation(),
            tour_navigation=FakeTourNavigation(),
            tour_stops=stops,
        )
    )

    payload = server.navigate_to_stop("entrance", ctx)

    assert payload["success"] is True
    assert payload["action_id"] == "action-1"
    assert payload["status"] == "completed"
    assert payload["stop_id"] == "entrance"


def test_navigate_to_stop_normalizes_failed_terminal_payload() -> None:
    tour_navigation = FakeTourNavigation()
    tour_navigation.navigate_result = {
        "success": False,
        "action_id": "action-1",
        "stop_id": "entrance",
        "stop_name": "Entrance",
        "outcome": "failed_recoverable",
        "detail": "Navigation failed.",
        "distance_remaining_m": 0.7,
        "recovery_count": 1,
        "replan_count": 0,
        "last_event_note": "Obstacle encountered.",
    }
    ctx = make_ctx(
        server.AppContext(
            publisher=FakePublisher(),
            camera=FakeCamera(),
            face_recognition=FakeFaceRecognition(),
            face_registration=FakeFaceRegistration(),
            navigation=FakeNavigation(),
            tour_navigation=tour_navigation,
            tour_stops=(TourStop("entrance", "Entrance", ("front door",), 0.0, 0.0, 1.0, "Start here."),),
        )
    )

    payload = server.navigate_to_stop("entrance", ctx)

    assert payload["success"] is False
    assert payload["action_id"] == "action-1"
    assert payload["status"] == "failed"
    assert payload["detail"] == "Navigation failed."


def test_list_tour_stops_returns_serialized_catalog() -> None:
    stops = (
        TourStop("entrance", "Entrance", ("front door",), 0.0, 0.0, 1.0, "Start here."),
        TourStop("lab", "Lab", ("electronics",), 1.0, 1.0, 1.0, "Build here."),
    )
    ctx = make_ctx(
        server.AppContext(
            publisher=FakePublisher(),
            camera=FakeCamera(),
            face_recognition=FakeFaceRecognition(),
            face_registration=FakeFaceRegistration(),
            navigation=FakeNavigation(),
            tour_navigation=FakeTourNavigation(),
            tour_stops=stops,
        )
    )

    payload = server.list_tour_stops(ctx)

    assert payload["success"] is True
    assert payload["count"] == 2
    assert payload["stops"][0]["stop_id"] == "entrance"
    assert "x" not in payload["stops"][0]


def test_navigate_to_stop_returns_structured_error_for_unknown_stop() -> None:
    ctx = make_ctx(
        server.AppContext(
            publisher=FakePublisher(),
            camera=FakeCamera(),
            face_recognition=FakeFaceRecognition(),
            face_registration=FakeFaceRegistration(),
            navigation=FakeNavigation(),
            tour_navigation=FakeTourNavigation(),
            tour_stops=(),
        )
    )

    payload = server.navigate_to_stop("missing", ctx)

    assert payload["success"] is False
    assert payload["stop_id"] == "missing"
    assert payload["available_stop_ids"] == []


def test_cancel_navigation_delegates_to_tour_navigation_provider() -> None:
    ctx = make_ctx(
        server.AppContext(
            publisher=FakePublisher(),
            camera=FakeCamera(),
            face_recognition=FakeFaceRecognition(),
            face_registration=FakeFaceRegistration(),
            navigation=FakeNavigation(),
            tour_navigation=FakeTourNavigation(),
            tour_stops=(),
        )
    )

    payload = server.cancel_navigation(ctx, action_id="action-1")

    assert payload["success"] is True
    assert payload["action_id"] == "action-1"


def test_rotate_angle_emits_session_correlation_when_meta_provided() -> None:
    observability = FakeObservability()
    ctx = make_ctx(
        server.AppContext(
            publisher=FakePublisher(),
            camera=FakeCamera(),
            face_recognition=FakeFaceRecognition(),
            face_registration=FakeFaceRegistration(),
            navigation=FakeNavigation(),
            tour_navigation=FakeTourNavigation(),
            observability=observability,
            tour_stops=(),
        ),
        meta={
            "session_id": "child-rotate-1",
            "parent_session_id": "main",
            "turn_id": "turn-rotate-1",
        },
    )

    payload = server.rotate_angle(ctx, angle_deg=5.0)

    assert payload["success"] is True
    assert len(observability.events) == 2
    start_event = observability.events[0]
    finish_event = observability.events[1]
    assert start_event["raw"]["session_id"] == "child-rotate-1"
    assert start_event["raw"]["parent_session_id"] == "main"
    assert start_event["raw"]["turn_id"] == "turn-rotate-1"
    assert finish_event["raw"]["session_id"] == "child-rotate-1"
    assert finish_event["raw"]["parent_session_id"] == "main"


def test_move_distance_emits_session_correlation_when_meta_provided() -> None:
    observability = FakeObservability()
    ctx = make_ctx(
        server.AppContext(
            publisher=FakePublisher(),
            camera=FakeCamera(),
            face_recognition=FakeFaceRecognition(),
            face_registration=FakeFaceRegistration(),
            navigation=FakeNavigation(),
            tour_navigation=FakeTourNavigation(),
            observability=observability,
            tour_stops=(),
        ),
        meta={
            "child_session_id": "child-move-1",
            "parent_session_id": "main",
            "turn_id": "turn-move-1",
        },
    )

    payload = server.move_distance(ctx, distance_m=0.5)

    assert payload["success"] is True
    assert len(observability.events) == 2
    assert observability.events[0]["raw"]["session_id"] == "child-move-1"
    assert observability.events[0]["raw"]["parent_session_id"] == "main"
    assert observability.events[1]["raw"]["turn_id"] == "turn-move-1"


def test_lifespan_degrades_cleanly_when_ros_startup_fails() -> None:
    created: dict[str, object] = {}

    class FailingPublisher(FakePublisher):
        def start(self) -> None:
            raise RuntimeError("publisher offline")

    class FailingNavigation(FakeNavigation):
        def start(self) -> None:
            raise RuntimeError("nav offline")

    class FailingCamera(FakeCamera):
        def start(self) -> None:
            raise RuntimeError("camera offline")

    class FailingFaceRecognition(FakeFaceRecognition):
        def start(self) -> None:
            raise RuntimeError("face offline")

    class FailingFaceRegistration(FakeFaceRegistration):
        def start(self) -> None:
            raise RuntimeError("face registration offline")

    class FailingTourNavigation(FakeTourNavigation):
        def start(self) -> None:
            raise RuntimeError("tour nav offline")

    async def run() -> None:
        with patch.object(server, "EyeExpressionPublisher", FailingPublisher), patch.object(
            server, "CameraCaptureProvider", FailingCamera
        ), patch.object(
            server, "FaceRecognitionStatusProvider", FailingFaceRecognition
        ), patch.object(
            server, "FaceRegistrationProvider", FailingFaceRegistration
        ), patch.object(
            server, "NavigationStatusProvider", FailingNavigation
        ), patch.object(
            server, "TourNavigationExecutor", FailingTourNavigation
        ), patch.object(server, "load_tour_stops", return_value=()):
            async with server.app_lifespan(server.mcp) as app_context:
                created["ctx"] = app_context

    asyncio.run(run())

    app_context = created["ctx"]
    assert app_context.publisher_start_error == "publisher offline"
    assert app_context.camera_start_error == "camera offline"
    assert app_context.face_recognition_start_error == "face offline"
    assert app_context.face_registration_start_error == "face registration offline"
    assert app_context.navigation_start_error == "nav offline"
    assert app_context.tour_navigation_start_error == "tour nav offline"
    assert isinstance(app_context.publisher, FailingPublisher)
    assert isinstance(app_context.navigation, FailingNavigation)


def test_is_loopback_host_recognizes_local_addresses() -> None:
    assert server._is_loopback_host("127.0.0.1") is True
    assert server._is_loopback_host("localhost") is True
    assert server._is_loopback_host("0.0.0.0") is False


def test_health_exposes_navigation_startup_error() -> None:
    tour_navigation = FakeTourNavigation()
    tour_navigation.health_payload["startup_error"] = "missing numpy"
    ctx = make_ctx(
        server.AppContext(
            publisher=FakePublisher(),
            camera=FakeCamera(),
            face_recognition=FakeFaceRecognition(),
            face_registration=FakeFaceRegistration(),
            navigation=FakeNavigation(),
            tour_navigation=tour_navigation,
            tour_stops=(),
            tour_navigation_start_error="missing numpy",
        )
    )

    payload = server.health(ctx)

    assert payload["navigation_ready"] is False
    assert payload["tour_navigation"]["startup_error"] == "missing numpy"
    assert payload["startup_errors"]["tour_navigation"] == "missing numpy"


def test_health_exposes_nav2_bypass_state() -> None:
    tour_navigation = FakeTourNavigation()
    tour_navigation.health_payload.update(
        {
            "nav2_ready": True,
            "nav2_import_ready": True,
            "nav2_active_check_bypassed": True,
            "readiness_detail": "Nav2 active-wait bypass enabled; runtime goal execution will determine actual readiness.",
        }
    )
    ctx = make_ctx(
        server.AppContext(
            publisher=FakePublisher(),
            camera=FakeCamera(),
            face_recognition=FakeFaceRecognition(),
            face_registration=FakeFaceRegistration(),
            navigation=FakeNavigation(),
            tour_navigation=tour_navigation,
            tour_stops=(),
        )
    )

    payload = server.health(ctx)

    assert payload["navigation_ready"] is True
    assert payload["tour_navigation"]["nav2_import_ready"] is True
    assert payload["tour_navigation"]["nav2_active_check_bypassed"] is True
    assert "runtime goal execution" in str(payload["tour_navigation"]["readiness_detail"]).lower()


def test_health_exposes_face_registration_startup_error() -> None:
    face_registration = FakeFaceRegistration()
    face_registration.health_payload["startup_error"] = "missing face_tracking_interfaces"
    ctx = make_ctx(
        server.AppContext(
            publisher=FakePublisher(),
            camera=FakeCamera(),
            face_recognition=FakeFaceRecognition(),
            face_registration=face_registration,
            navigation=FakeNavigation(),
            tour_navigation=FakeTourNavigation(),
            tour_stops=(),
            face_registration_start_error="missing face_tracking_interfaces",
        )
    )

    payload = server.health(ctx)

    assert payload["face_registration_ready"] is False
    assert payload["face_registration"]["startup_error"] == "missing face_tracking_interfaces"
    assert payload["startup_errors"]["face_registration"] == "missing face_tracking_interfaces"
