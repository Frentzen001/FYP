from __future__ import annotations

import math
import os
import threading
import time
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from .tour_stops import TourStop

ROS2_IMPORT_ERROR: str | None = None
try:
    import rclpy
    from geometry_msgs.msg import PoseStamped
except ImportError as exc:
    ROS2_IMPORT_ERROR = str(exc)
    rclpy = None  # type: ignore[assignment]
    PoseStamped = object  # type: ignore[assignment,misc]
    ROS2_AVAILABLE = False
else:
    ROS2_AVAILABLE = True

NAV2_IMPORT_ERROR: str | None = None
try:
    from nav2_simple_commander.robot_navigator import BasicNavigator, TaskResult
except ImportError as exc:
    NAV2_IMPORT_ERROR = str(exc)
    rclpy = None  # type: ignore[assignment]
    BasicNavigator = object  # type: ignore[assignment,misc]
    TaskResult = object  # type: ignore[assignment,misc]
    NAV2_AVAILABLE = False
else:
    NAV2_AVAILABLE = True


class TourNavigationExecutor:
    def __init__(self) -> None:
        self._bypass_active_wait = os.getenv("MORETEA_BYPASS_NAV2_ACTIVE_WAIT", "1").strip().lower() in {
            "1",
            "true",
            "yes",
        }
        self._navigator: Any = None
        self._started = False
        self._startup_error: str | None = None
        self._readiness_detail = "Nav2 commander has not been initialized."
        self._nav2_import_ready = False
        self._lock = threading.Lock()
        self._worker_thread: threading.Thread | None = None
        self._nav_active = False
        self._cancel_requested = False
        self._distance_remaining: float | None = None
        self._recovery_count = 0
        self._replan_count = 0
        self._last_event_note: str | None = None
        self._active_stop_id: str | None = None
        self._active_stop_name: str | None = None
        self._last_outcome: str | None = None
        self._action_id: str | None = None
        self._session_id: str | None = None
        self._turn_id: str | None = None
        self._status = "idle"
        self._detail = "No navigation action has been started."
        self._created_at: str | None = None
        self._started_at: str | None = None
        self._completed_at: str | None = None
        self._last_updated_at: str | None = None

    def start(self) -> None:
        if not ROS2_AVAILABLE:
            detail = ROS2_IMPORT_ERROR or "unknown ROS 2 import error"
            self._startup_error = (
                "ROS 2 Python dependencies are unavailable. "
                f"Source the ROS 2 Humble environment before starting the server. Detail: {detail}"
            )
            raise RuntimeError(self._startup_error)
        if not NAV2_AVAILABLE:
            detail = NAV2_IMPORT_ERROR or "unknown Nav2 import error"
            if "numpy" in detail.lower():
                self._startup_error = (
                    "Nav2 simple commander import failed because a Python dependency is missing in the uv environment. "
                    f"Install the missing dependency and retry. Detail: {detail}"
                )
            else:
                self._startup_error = (
                    "Nav2 simple commander is unavailable. Install or source the ROS 2 Humble navigation environment before starting the server. "
                    f"Detail: {detail}"
                )
            raise RuntimeError(self._startup_error)
        if self._started:
            return

        self._startup_error = None
        self._nav2_import_ready = False
        if not rclpy.ok():
            rclpy.init()

        navigator = BasicNavigator()
        self._navigator = navigator
        self._nav2_import_ready = True
        self._started = True
        if self._bypass_active_wait:
            self._readiness_detail = (
                "Nav2 active-wait bypass enabled; runtime goal execution will determine actual readiness."
            )
            return

        try:
            navigator.waitUntilNav2Active()
        except Exception as exc:  # noqa: BLE001
            self._startup_error = f"Nav2 failed to become active: {exc}"
            self._readiness_detail = self._startup_error
            try:
                navigator.destroy_node()
            except Exception:  # noqa: BLE001
                pass
            self._navigator = None
            self._started = False
            raise RuntimeError(self._startup_error) from exc

        self._readiness_detail = "Nav2 is active and ready to accept goals."

    def shutdown(self) -> None:
        with self._lock:
            self._cancel_requested = True
        worker_thread = self._worker_thread
        if worker_thread is not None and worker_thread.is_alive():
            worker_thread.join(timeout=1.0)
        if self._navigator is not None:
            try:
                self._navigator.destroy_node()
            finally:
                self._navigator = None
        with self._lock:
            self._started = False
            self._nav2_import_ready = False
            self._nav_active = False
            self._cancel_requested = False
            self._distance_remaining = None
            self._recovery_count = 0
            self._replan_count = 0
            self._last_event_note = None
            self._active_stop_id = None
            self._active_stop_name = None
            self._worker_thread = None
            self._readiness_detail = "Nav2 commander has not been initialized."

    def health(self) -> dict[str, object]:
        with self._lock:
            active_stop_id = self._active_stop_id
            active_goal = self._nav_active
            action_id = self._action_id
        return {
            "success": True,
            "nav2_ready": bool(self._started and self._navigator is not None),
            "nav2_import_ready": self._nav2_import_ready,
            "nav2_active_check_bypassed": self._bypass_active_wait,
            "active_goal": active_goal,
            "active_stop_id": active_stop_id,
            "current_action_id": action_id,
            "startup_error": self._startup_error,
            "readiness_detail": self._readiness_detail,
        }

    def start_navigation_to_stop(
        self,
        stop: TourStop,
        session_id: str | None = None,
        turn_id: str | None = None,
    ) -> dict[str, object]:
        if not self._started or self._navigator is None:
            return self._action_payload(
                success=False,
                status="failed",
                stop=stop,
                detail="Navigation unavailable (Nav2 not loaded).",
                session_id=session_id,
                turn_id=turn_id,
            )

        with self._lock:
            if self._nav_active:
                return self._action_payload(
                    success=False,
                    status=self._status,
                    stop=stop,
                    detail="Another navigation action is already running.",
                    action_id=self._action_id,
                    session_id=self._session_id,
                    turn_id=self._turn_id,
                )

            action_id = str(uuid4())
            created_at = _now_iso()
            self._nav_active = True
            self._cancel_requested = False
            self._distance_remaining = None
            self._recovery_count = 0
            self._replan_count = 0
            self._last_event_note = None
            self._active_stop_id = stop.id
            self._active_stop_name = stop.name
            self._last_outcome = None
            self._action_id = action_id
            self._session_id = session_id
            self._turn_id = turn_id
            self._status = "accepted"
            self._detail = "Navigation accepted."
            self._created_at = created_at
            self._started_at = None
            self._completed_at = None
            self._last_updated_at = created_at
            self._worker_thread = threading.Thread(
                target=self._run_navigation,
                args=(action_id, stop),
                daemon=True,
                name=f"moretea_nav_{action_id[:8]}",
            )
            self._worker_thread.start()
            return self._snapshot_locked(success=True)

    def get_navigation_action_status(self, action_id: str) -> dict[str, object]:
        with self._lock:
            if self._action_id is None:
                return {
                    "success": False,
                    "error": "No navigation action has been started.",
                    "action_id": action_id,
                }
            if action_id != self._action_id:
                return {
                    "success": False,
                    "error": f"Unknown action_id '{action_id}'.",
                    "action_id": action_id,
                    "current_action_id": self._action_id,
                }
            return self._snapshot_locked(success=True)

    def navigate_to_stop(self, stop: TourStop) -> dict[str, object]:
        start_payload = self.start_navigation_to_stop(stop)
        action_id = start_payload.get("action_id")
        if not start_payload.get("success") or not isinstance(action_id, str):
            return self._compatibility_payload(stop, start_payload)
        while True:
            status_payload = self.get_navigation_action_status(action_id)
            status = status_payload.get("status")
            if status in {"completed", "failed", "cancelled", "timed_out"}:
                return self._compatibility_payload(stop, status_payload)
            time.sleep(0.05)

    def cancel_navigation(self, action_id: str | None = None) -> dict[str, object]:
        with self._lock:
            current_action_id = self._action_id
            current_status = self._status
            active_goal = self._nav_active
            active_stop_id = self._active_stop_id
            if action_id is not None and current_action_id is not None and action_id != current_action_id:
                return {
                    "success": False,
                    "error": f"Unknown action_id '{action_id}'.",
                    "action_id": action_id,
                    "current_action_id": current_action_id,
                }
            self._cancel_requested = True
        return {
            "success": True,
            "action_id": current_action_id,
            "status": current_status if active_goal else "cancelled",
            "active_goal": active_goal,
            "active_stop_id": active_stop_id,
            "detail": "Cancellation requested." if active_goal else "No active navigation task to cancel.",
        }

    def current_status(self) -> dict[str, object]:
        with self._lock:
            return {
                "success": True,
                "active_goal": self._nav_active,
                "active_stop_id": self._active_stop_id,
                "active_stop_name": self._active_stop_name,
                "distance_remaining_m": self._distance_remaining,
                "recovery_count": self._recovery_count,
                "replan_count": self._replan_count,
                "last_event_note": self._last_event_note,
                "last_outcome": self._last_outcome,
                "action_id": self._action_id,
                "status": self._status,
                "detail": self._detail,
                "created_at": self._created_at,
                "started_at": self._started_at,
                "completed_at": self._completed_at,
                "last_updated_at": self._last_updated_at,
                "session_id": self._session_id,
                "turn_id": self._turn_id,
            }

    def _run_navigation(self, action_id: str, stop: TourStop) -> None:
        pose = self._make_pose(stop.x, stop.y, stop.ow)
        close_enough_cycles = 0
        self._set_running(action_id, "Navigation is in progress.")
        try:
            self._navigator.goToPose(pose)
            while True:
                if self._navigator.isTaskComplete():
                    break
                with self._lock:
                    if action_id != self._action_id:
                        return
                    cancel_requested = self._cancel_requested
                if cancel_requested:
                    self._navigator.cancelTask()
                    self._finish_action(action_id, "cancelled", "Navigation cancelled by request.", stop)
                    return

                feedback = self._navigator.getFeedback()
                if feedback is not None:
                    close_enough_cycles = self._apply_feedback(action_id, feedback, close_enough_cycles)
                    if close_enough_cycles >= 5:
                        self._finish_action(
                            action_id,
                            "completed",
                            "Reached destination using close-enough fallback.",
                            stop,
                        )
                        return
                time.sleep(0.05)

            result = self._navigator.getResult()
            if result == getattr(TaskResult, "SUCCEEDED", None):
                self._finish_action(action_id, "completed", "Reached destination.", stop)
                return
            if result == getattr(TaskResult, "CANCELED", None):
                self._finish_action(action_id, "cancelled", "Navigation cancelled.", stop)
                return
            self._finish_action(action_id, "failed", "Navigation failed.", stop)
        except Exception as exc:  # noqa: BLE001
            self._finish_action(action_id, "failed", f"Navigation failed: {exc}", stop)

    def _set_running(self, action_id: str, detail: str) -> None:
        with self._lock:
            if action_id != self._action_id:
                return
            self._status = "running"
            self._detail = detail
            if self._started_at is None:
                self._started_at = _now_iso()
            self._last_updated_at = _now_iso()

    def _apply_feedback(self, action_id: str, feedback: Any, close_enough_cycles: int) -> int:
        with self._lock:
            if action_id != self._action_id:
                return close_enough_cycles
            distance_remaining = getattr(feedback, "distance_remaining", None)
            if isinstance(distance_remaining, (int, float)):
                self._distance_remaining = float(distance_remaining)
                if float(distance_remaining) < 0.5:
                    close_enough_cycles += 1
                else:
                    close_enough_cycles = 0

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

            self._last_updated_at = _now_iso()
        return close_enough_cycles

    def _finish_action(self, action_id: str, status: str, detail: str, stop: TourStop) -> None:
        with self._lock:
            if action_id != self._action_id:
                return
            self._nav_active = False
            self._status = status
            self._detail = detail
            self._completed_at = _now_iso()
            self._last_updated_at = self._completed_at
            self._last_outcome = _status_to_outcome(status)
            self._active_stop_id = stop.id
            self._active_stop_name = stop.name
            self._worker_thread = None

    def _snapshot_locked(self, *, success: bool) -> dict[str, object]:
        return {
            "success": success,
            "action_id": self._action_id,
            "session_id": self._session_id,
            "turn_id": self._turn_id,
            "status": self._status,
            "stop_id": self._active_stop_id,
            "stop_name": self._active_stop_name,
            "distance_remaining_m": self._distance_remaining,
            "recovery_count": self._recovery_count,
            "replan_count": self._replan_count,
            "last_event_note": self._last_event_note,
            "detail": self._detail,
            "created_at": self._created_at,
            "started_at": self._started_at,
            "completed_at": self._completed_at,
            "last_updated_at": self._last_updated_at,
        }

    def _action_payload(
        self,
        *,
        success: bool,
        status: str,
        stop: TourStop,
        detail: str,
        action_id: str | None = None,
        session_id: str | None = None,
        turn_id: str | None = None,
    ) -> dict[str, object]:
        timestamp = _now_iso()
        return {
            "success": success,
            "action_id": action_id,
            "session_id": session_id,
            "turn_id": turn_id,
            "status": status,
            "stop_id": stop.id,
            "stop_name": stop.name,
            "distance_remaining_m": None,
            "recovery_count": 0,
            "replan_count": 0,
            "last_event_note": None,
            "detail": detail,
            "created_at": timestamp,
            "started_at": None,
            "completed_at": timestamp if status in {"completed", "failed", "cancelled", "timed_out"} else None,
            "last_updated_at": timestamp,
        }

    def _make_pose(self, x: float, y: float, ow: float) -> Any:
        oz = math.sqrt(max(0.0, 1.0 - ow**2))
        pose = PoseStamped()
        pose.header.frame_id = "map"
        pose.header.stamp = self._navigator.get_clock().now().to_msg()
        pose.pose.position.x = float(x)
        pose.pose.position.y = float(y)
        pose.pose.position.z = 0.0
        pose.pose.orientation.x = 0.0
        pose.pose.orientation.y = 0.0
        pose.pose.orientation.z = oz
        pose.pose.orientation.w = float(ow)
        return pose

    def _compatibility_payload(self, stop: TourStop, payload: dict[str, object]) -> dict[str, object]:
        status = str(payload.get("status", "failed"))
        outcome = _status_to_outcome(status)
        return {
            "success": outcome in {"succeeded", "canceled"},
            "action_id": payload.get("action_id"),
            "stop_id": stop.id,
            "stop_name": stop.name,
            "outcome": outcome,
            "detail": payload.get("detail"),
            "distance_remaining_m": payload.get("distance_remaining_m"),
            "recovery_count": payload.get("recovery_count", 0),
            "replan_count": payload.get("replan_count", 0),
            "last_event_note": payload.get("last_event_note"),
        }


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _status_to_outcome(status: str) -> str:
    if status == "completed":
        return "succeeded"
    if status == "cancelled":
        return "canceled"
    if status == "timed_out":
        return "failed_recoverable"
    return "failed_recoverable"
