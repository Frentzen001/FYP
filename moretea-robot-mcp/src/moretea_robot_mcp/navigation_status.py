from __future__ import annotations

import threading
from dataclasses import dataclass
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
    from action_msgs.msg import GoalStatus, GoalStatusArray
    from nav2_msgs.action import NavigateToPose

    NAV2_STATUS_AVAILABLE = True
except ImportError:
    NAV2_STATUS_AVAILABLE = False
    GoalStatus = object  # type: ignore[assignment,misc]
    GoalStatusArray = object  # type: ignore[assignment,misc]
    NavigateToPose = None  # type: ignore[assignment]


NAVIGATION_STATUS_TOPIC = "/navigate_to_pose/_action/status"
NAVIGATION_FEEDBACK_TOPIC = "/navigate_to_pose/_action/feedback"
_ACTIVE_GOAL_STATUSES = frozenset(
    {
        getattr(GoalStatus, "STATUS_ACCEPTED", 1),
        getattr(GoalStatus, "STATUS_EXECUTING", 2),
        getattr(GoalStatus, "STATUS_CANCELING", 3),
    }
)


@dataclass(frozen=True)
class NavigationSnapshot:
    success: bool
    available: bool
    is_navigating: bool
    distance_remaining_m: float | None
    recovery_count: int
    replan_count: int
    last_event_note: str | None


def format_navigation_status_text(
    available: bool,
    is_navigating: bool,
    distance_remaining_m: float | None,
) -> str:
    if not available:
        return "Navigation is unavailable."
    if not is_navigating:
        return "The robot is not currently navigating."
    if distance_remaining_m is None:
        return "The robot is navigating, but distance feedback is not available yet."
    return f"Approximately {distance_remaining_m:.1f} metres remain."


def build_navigation_status(snapshot: NavigationSnapshot) -> dict[str, object]:
    return {
        "success": snapshot.success,
        "available": snapshot.available,
        "is_navigating": snapshot.is_navigating,
        "distance_remaining_m": snapshot.distance_remaining_m,
        "recovery_count": snapshot.recovery_count,
        "replan_count": snapshot.replan_count,
        "last_event_note": snapshot.last_event_note,
        "status_text": format_navigation_status_text(
            available=snapshot.available,
            is_navigating=snapshot.is_navigating,
            distance_remaining_m=snapshot.distance_remaining_m,
        ),
    }


class NavigationStatusProvider:
    def __init__(
        self,
        status_topic: str = NAVIGATION_STATUS_TOPIC,
        feedback_topic: str = NAVIGATION_FEEDBACK_TOPIC,
    ) -> None:
        self._status_topic = status_topic
        self._feedback_topic = feedback_topic
        self._node: Any = None
        self._executor: Any = None
        self._spin_thread: threading.Thread | None = None
        self._started = False
        self._startup_error: str | None = None
        self._lock = threading.Lock()
        self._is_navigating = False
        self._distance_remaining_m: float | None = None
        self._recovery_count = 0
        self._replan_count = 0
        self._last_event_note: str | None = None

    def start(self) -> None:
        if not ROS2_AVAILABLE:
            self._startup_error = (
                "ROS 2 Python dependencies are unavailable. Source the ROS 2 Humble environment before starting the server."
            )
            raise RuntimeError(self._startup_error)
        if self._started:
            return

        self._startup_error = None
        self._started = True
        if not NAV2_STATUS_AVAILABLE:
            return

        if not rclpy.ok():
            rclpy.init()

        self._node = Node("moretea_navigation_status")
        feedback_message_type = NavigateToPose.Impl.FeedbackMessage
        self._node.create_subscription(
            GoalStatusArray,
            self._status_topic,
            self._on_status,
            10,
        )
        self._node.create_subscription(
            feedback_message_type,
            self._feedback_topic,
            self._on_feedback,
            10,
        )

        self._executor = rclpy.executors.MultiThreadedExecutor()
        self._executor.add_node(self._node)
        self._spin_thread = threading.Thread(
            target=self._executor.spin,
            daemon=True,
            name="moretea_navigation_status_spin",
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
                self._is_navigating = False
                self._distance_remaining_m = None
                self._recovery_count = 0
                self._replan_count = 0
                self._last_event_note = None
            self._started = False
            self._node = None
            self._executor = None
            self._spin_thread = None

    def health(self) -> dict[str, object]:
        return {
            "success": True,
            "ros_ready": bool(ROS2_AVAILABLE and self._started),
            "nav2_ready": bool(self._started and NAV2_STATUS_AVAILABLE),
            "status_topic": self._status_topic,
            "feedback_topic": self._feedback_topic,
            "startup_error": self._startup_error,
        }

    def status(self) -> dict[str, object]:
        with self._lock:
            snapshot = NavigationSnapshot(
                success=True,
                available=bool(self._started and NAV2_STATUS_AVAILABLE),
                is_navigating=self._is_navigating,
                distance_remaining_m=self._distance_remaining_m,
                recovery_count=self._recovery_count,
                replan_count=self._replan_count,
                last_event_note=self._last_event_note,
            )
        return build_navigation_status(snapshot)

    def _on_status(self, msg: GoalStatusArray) -> None:
        statuses = getattr(msg, "status_list", [])
        is_navigating = any(
            getattr(item, "status", GoalStatus.STATUS_UNKNOWN) in _ACTIVE_GOAL_STATUSES
            for item in statuses
        )
        with self._lock:
            self._is_navigating = is_navigating
            if not is_navigating:
                self._distance_remaining_m = None
                self._recovery_count = 0
                self._replan_count = 0
                self._last_event_note = None

    def _on_feedback(self, msg: Any) -> None:
        feedback = getattr(msg, "feedback", None)
        if feedback is None:
            return

        with self._lock:
            self._is_navigating = True
            self._distance_remaining_m = getattr(feedback, "distance_remaining", None)

            recoveries = getattr(feedback, "number_of_recoveries", None)
            if isinstance(recoveries, int):
                if recoveries > self._recovery_count:
                    self._last_event_note = "I am taking a moment to recover around an obstacle."
                self._recovery_count = recoveries

            replans = getattr(feedback, "number_of_replans", None)
            if isinstance(replans, int):
                if replans > self._replan_count:
                    self._last_event_note = "I am taking a slightly different route to stay safe."
                self._replan_count = replans
