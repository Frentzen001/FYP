from __future__ import annotations

import threading
import time
from types import SimpleNamespace
from unittest.mock import patch

import moretea_robot_mcp.tour_navigation as tour_navigation
from moretea_robot_mcp.tour_navigation import TourNavigationExecutor
from moretea_robot_mcp.tour_stops import TourStop


class FakeTaskResult:
    SUCCEEDED = "succeeded"
    CANCELED = "canceled"
    FAILED = "failed"


class FakePoseStamped:
    def __init__(self) -> None:
        self.header = SimpleNamespace(frame_id=None, stamp=None)
        self.pose = SimpleNamespace(
            position=SimpleNamespace(x=0.0, y=0.0, z=0.0),
            orientation=SimpleNamespace(x=0.0, y=0.0, z=0.0, w=1.0),
        )


class FakeNavigator:
    def __init__(self) -> None:
        self.goal_sent = False
        self.cancelled = False
        self.destroyed = False
        self.feedbacks = [
            SimpleNamespace(distance_remaining=1.2, number_of_recoveries=0, number_of_replans=0),
            SimpleNamespace(distance_remaining=0.4, number_of_recoveries=1, number_of_replans=1),
        ]
        self.polls = 0
        self.result = FakeTaskResult.SUCCEEDED

    def waitUntilNav2Active(self) -> None:
        return None

    def get_clock(self) -> SimpleNamespace:
        return SimpleNamespace(now=lambda: SimpleNamespace(to_msg=lambda: "stamp"))

    def goToPose(self, pose) -> None:
        self.goal_sent = True

    def isTaskComplete(self) -> bool:
        self.polls += 1
        return self.polls >= 3

    def getFeedback(self):
        if self.feedbacks:
            return self.feedbacks.pop(0)
        return None

    def cancelTask(self) -> None:
        self.cancelled = True
        self.result = FakeTaskResult.CANCELED

    def getResult(self):
        return self.result

    def destroy_node(self) -> None:
        self.destroyed = True


STOP = TourStop(
    id="entrance",
    name="Entrance",
    aliases=("front door",),
    x=0.0,
    y=0.0,
    ow=1.0,
    narration="Start here.",
)


def test_start_initializes_humble_navigator() -> None:
    executor = TourNavigationExecutor()

    with patch.object(tour_navigation, "NAV2_AVAILABLE", True), patch.object(
        tour_navigation, "BasicNavigator", FakeNavigator
    ), patch.object(tour_navigation, "PoseStamped", FakePoseStamped), patch.object(
        tour_navigation, "TaskResult", FakeTaskResult
    ), patch.object(
        tour_navigation, "rclpy", SimpleNamespace(ok=lambda: True)
    ):
        executor.start()

    health = executor.health()
    assert health["nav2_ready"] is True
    assert health["nav2_import_ready"] is True
    assert health["nav2_active_check_bypassed"] is True
    assert "bypass enabled" in str(health["readiness_detail"]).lower()


def test_start_navigation_to_stop_returns_action_metadata() -> None:
    executor = TourNavigationExecutor()

    with patch.object(tour_navigation, "NAV2_AVAILABLE", True), patch.object(
        tour_navigation, "BasicNavigator", FakeNavigator
    ), patch.object(tour_navigation, "PoseStamped", FakePoseStamped), patch.object(
        tour_navigation, "TaskResult", FakeTaskResult
    ), patch.object(
        tour_navigation, "rclpy", SimpleNamespace(ok=lambda: True)
    ):
        executor.start()
        start_payload = executor.start_navigation_to_stop(STOP)

    assert start_payload["success"] is True
    assert start_payload["status"] in {"accepted", "running"}
    assert isinstance(start_payload["action_id"], str)


def test_navigate_to_stop_reports_feedback_derived_fields() -> None:
    executor = TourNavigationExecutor()

    with patch.object(tour_navigation, "NAV2_AVAILABLE", True), patch.object(
        tour_navigation, "BasicNavigator", FakeNavigator
    ), patch.object(tour_navigation, "PoseStamped", FakePoseStamped), patch.object(
        tour_navigation, "TaskResult", FakeTaskResult
    ), patch.object(
        tour_navigation, "rclpy", SimpleNamespace(ok=lambda: True)
    ):
        executor.start()
        payload = executor.navigate_to_stop(STOP)

    assert payload["outcome"] == "succeeded"
    assert payload["stop_id"] == "entrance"
    assert payload["recovery_count"] == 1
    assert payload["replan_count"] == 1
    assert payload["last_event_note"] == "I am taking a slightly different route to stay safe."


def test_cancel_navigation_is_idempotent_without_active_goal() -> None:
    executor = TourNavigationExecutor()

    payload = executor.cancel_navigation()

    assert payload["success"] is True
    assert payload["active_goal"] is False


def test_cancel_navigation_interrupts_active_goal() -> None:
    executor = TourNavigationExecutor()

    class SlowNavigator(FakeNavigator):
        def isTaskComplete(self) -> bool:
            self.polls += 1
            time.sleep(0.02)
            return False

    with patch.object(tour_navigation, "NAV2_AVAILABLE", True), patch.object(
        tour_navigation, "BasicNavigator", SlowNavigator
    ), patch.object(tour_navigation, "PoseStamped", FakePoseStamped), patch.object(
        tour_navigation, "TaskResult", FakeTaskResult
    ), patch.object(
        tour_navigation, "rclpy", SimpleNamespace(ok=lambda: True)
    ):
        executor.start()
        captured: dict[str, object] = {}

        def run_navigation() -> None:
            captured["start_payload"] = executor.start_navigation_to_stop(STOP)
            while True:
                status = executor.get_navigation_action_status(captured["start_payload"]["action_id"])
                if status["status"] in {"completed", "failed", "cancelled", "timed_out"}:
                    captured["payload"] = status
                    return
                time.sleep(0.01)

        thread = threading.Thread(target=run_navigation)
        thread.start()
        time.sleep(0.05)
        cancel_payload = executor.cancel_navigation()
        thread.join(timeout=1)

    assert cancel_payload["active_goal"] is True
    assert captured["payload"]["status"] == "cancelled"


def test_get_navigation_action_status_rejects_unknown_action_id() -> None:
    executor = TourNavigationExecutor()

    payload = executor.get_navigation_action_status("missing")

    assert payload["success"] is False
    assert payload["action_id"] == "missing"


def test_start_reports_missing_numpy_clearly() -> None:
    executor = TourNavigationExecutor()

    with patch.object(tour_navigation, "ROS2_AVAILABLE", True), patch.object(
        tour_navigation, "NAV2_AVAILABLE", False
    ), patch.object(
        tour_navigation, "NAV2_IMPORT_ERROR", "No module named 'numpy'"
    ):
        try:
            executor.start()
        except RuntimeError as exc:
            message = str(exc)
        else:  # pragma: no cover - defensive
            raise AssertionError("Expected RuntimeError")

    assert "missing dependency" in message
    assert "numpy" in message


def test_start_waits_for_nav2_when_bypass_disabled() -> None:
    executor = TourNavigationExecutor()
    executor._bypass_active_wait = False

    with patch.object(tour_navigation, "NAV2_AVAILABLE", True), patch.object(
        tour_navigation, "BasicNavigator", FakeNavigator
    ), patch.object(tour_navigation, "PoseStamped", FakePoseStamped), patch.object(
        tour_navigation, "TaskResult", FakeTaskResult
    ), patch.object(
        tour_navigation, "rclpy", SimpleNamespace(ok=lambda: True)
    ):
        executor.start()

    health = executor.health()
    assert health["nav2_ready"] is True
    assert health["nav2_active_check_bypassed"] is False
    assert "ready to accept goals" in str(health["readiness_detail"]).lower()
