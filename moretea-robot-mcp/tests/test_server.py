from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import patch

from moretea_robot_mcp import server
from moretea_robot_mcp.tour_stops import TourStop


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


def make_ctx(app_context: server.AppContext):
    return SimpleNamespace(request_context=SimpleNamespace(lifespan_context=app_context))


def test_health_reports_nested_provider_statuses() -> None:
    ctx = make_ctx(
        server.AppContext(
            publisher=FakePublisher(),
            navigation=FakeNavigation(),
            tour_navigation=FakeTourNavigation(),
            tour_stops=(),
        )
    )

    payload = server.health(ctx)

    assert payload["success"] is True
    assert payload["robot_control_ready"] is False
    assert payload["navigation_ready"] is False
    assert payload["publisher"]["topic"] == "/eye_expression"
    assert payload["navigation"]["status_topic"] == "/navigate_to_pose/_action/status"
    assert payload["tour_navigation"]["active_goal"] is False
    assert payload["tour_navigation"]["nav2_active_check_bypassed"] is True
    assert payload["startup_errors"] == {
        "publisher": None,
        "navigation": None,
        "tour_navigation": None,
        "tour_stops": None,
    }


def test_express_emotion_returns_structured_error_for_invalid_mood() -> None:
    publisher = FakePublisher()
    publisher.publish_result = ValueError("Unsupported emotion 'curious'.")
    ctx = make_ctx(
        server.AppContext(
            publisher=publisher,
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
            navigation=navigation,
            tour_navigation=FakeTourNavigation(),
            tour_stops=(),
        )
    )

    payload = server.get_navigation_status(ctx)

    assert payload["success"] is True
    assert payload["is_navigating"] is True
    assert payload["distance_remaining_m"] == 1.5


def test_start_navigation_to_stop_returns_action_payload() -> None:
    stops = (
        TourStop("entrance", "Entrance", ("front door",), 0.0, 0.0, 1.0, "Start here."),
    )
    ctx = make_ctx(
        server.AppContext(
            publisher=FakePublisher(),
            navigation=FakeNavigation(),
            tour_navigation=FakeTourNavigation(),
            tour_stops=stops,
        )
    )

    payload = server.start_navigation_to_stop("entrance", ctx, session_id="s1", turn_id="t1")

    assert payload["success"] is True
    assert payload["action_id"] == "action-1"
    assert payload["session_id"] == "s1"
    assert payload["turn_id"] == "t1"


def test_get_navigation_action_status_delegates_to_provider() -> None:
    ctx = make_ctx(
        server.AppContext(
            publisher=FakePublisher(),
            navigation=FakeNavigation(),
            tour_navigation=FakeTourNavigation(),
            tour_stops=(),
        )
    )

    payload = server.get_navigation_action_status("action-1", ctx)

    assert payload["success"] is True
    assert payload["action_id"] == "action-1"
    assert payload["status"] == "running"


def test_list_tour_stops_returns_serialized_catalog() -> None:
    stops = (
        TourStop("entrance", "Entrance", ("front door",), 0.0, 0.0, 1.0, "Start here."),
        TourStop("lab", "Lab", ("electronics",), 1.0, 1.0, 1.0, "Build here."),
    )
    ctx = make_ctx(
        server.AppContext(
            publisher=FakePublisher(),
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
            navigation=FakeNavigation(),
            tour_navigation=FakeTourNavigation(),
            tour_stops=(),
        )
    )

    payload = server.cancel_navigation(ctx, action_id="action-1")

    assert payload["success"] is True
    assert payload["action_id"] == "action-1"


def test_lifespan_degrades_cleanly_when_ros_startup_fails() -> None:
    created: dict[str, object] = {}

    class FailingPublisher(FakePublisher):
        def start(self) -> None:
            raise RuntimeError("publisher offline")

    class FailingNavigation(FakeNavigation):
        def start(self) -> None:
            raise RuntimeError("nav offline")

    class FailingTourNavigation(FakeTourNavigation):
        def start(self) -> None:
            raise RuntimeError("tour nav offline")

    async def run() -> None:
        with patch.object(server, "EyeExpressionPublisher", FailingPublisher), patch.object(
            server, "NavigationStatusProvider", FailingNavigation
        ), patch.object(
            server, "TourNavigationExecutor", FailingTourNavigation
        ), patch.object(
            server, "load_tour_stops", return_value=()
        ):
            async with server.app_lifespan(server.mcp) as app_context:
                created["ctx"] = app_context

    asyncio.run(run())

    app_context = created["ctx"]
    assert app_context.publisher_start_error == "publisher offline"
    assert app_context.navigation_start_error == "nav offline"
    assert app_context.tour_navigation_start_error == "tour nav offline"
    assert app_context.publisher.shutdown_called is True
    assert app_context.navigation.shutdown_called is True
    assert app_context.tour_navigation.shutdown_called is True


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
