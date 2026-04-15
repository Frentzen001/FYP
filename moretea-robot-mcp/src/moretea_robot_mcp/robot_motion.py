from __future__ import annotations

import os
import threading
import time
from typing import Any, Callable

CMD_VEL_TOPIC = "/cmd_vel"
MAX_LINEAR_VEL = 0.4   # m/s — matches SKILL.md safety limit
MAX_ANGULAR_VEL = 0.8  # rad/s — matches SKILL.md safety limit
MAX_LINEAR_DURATION_S = 10.0   # hard cap for linear motion — 10 s × 0.4 m/s = 4 m max
MAX_ANGULAR_DURATION_S = 30.0  # hard cap for angular motion — allows slow robots to finish 180°+

try:
    import rclpy
    import rclpy.executors
    from geometry_msgs.msg import Twist
    from rclpy.node import Node

    ROS2_AVAILABLE = True
except ImportError:
    ROS2_AVAILABLE = False
    rclpy = None  # type: ignore[assignment]
    Node = object  # type: ignore[assignment,misc]
    Twist = object  # type: ignore[assignment,misc]


def _clamp(value: float, limit: float) -> float:
    return max(-limit, min(limit, value))


def _signed_angle_diff(a: float, b: float) -> float:
    """Shortest signed rotation from angle b to angle a, result in (-π, π]."""
    import math
    d = a - b
    while d > math.pi:
        d -= 2 * math.pi
    while d <= -math.pi:
        d += 2 * math.pi
    return d


def _motion_confirmation_required_payload(kind: str) -> dict[str, object]:
    return {
        "success": False,
        "error": (
            "Closed-loop motion confirmation is unavailable. "
            f"Refusing {kind} without fresh odometry. Pass allow_open_loop=True to override."
        ),
        "requires_confirmation": True,
        "allow_open_loop": False,
    }


def _feedback_lost_payload(kind: str) -> dict[str, object]:
    return {
        "success": False,
        "error": (
            "Closed-loop motion confirmation became unavailable during execution. "
            f"{kind.capitalize()} was stopped because odometry feedback is stale."
        ),
        "requires_confirmation": True,
        "feedback_stale": True,
    }


class RobotMotionProvider:
    """Publishes velocity commands to /cmd_vel with safety clamping."""

    def __init__(self, topic: str = CMD_VEL_TOPIC) -> None:
        self._topic = topic
        self._node: Any = None
        self._executor: Any = None
        self._publisher: Any = None
        self._spin_thread: threading.Thread | None = None
        self._started = False
        self._startup_error: str | None = None
        self._lock = threading.Lock()
        self._motion_active = False

    def start(self) -> None:
        if not ROS2_AVAILABLE:
            self._startup_error = (
                "ROS 2 Python dependencies are unavailable. "
                "Source the ROS 2 Humble environment before starting the server."
            )
            raise RuntimeError(self._startup_error)
        if self._started:
            return

        self._startup_error = None
        if not rclpy.ok():
            rclpy.init()

        self._node = Node("moretea_robot_motion")
        self._publisher = self._node.create_publisher(Twist, self._topic, 10)
        self._executor = rclpy.executors.MultiThreadedExecutor()
        self._executor.add_node(self._node)
        self._spin_thread = threading.Thread(
            target=self._executor.spin,
            daemon=True,
            name="moretea_robot_motion_spin",
        )
        self._spin_thread.start()
        self._started = True

    def shutdown(self) -> None:
        if not self._started:
            return
        self._publish_zero()
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
            self._started = False
            self._publisher = None
            self._node = None
            self._executor = None
            self._spin_thread = None

    def health(self) -> dict[str, object]:
        return {
            "success": True,
            "ros_ready": bool(ROS2_AVAILABLE and self._started),
            "topic": self._topic,
            "max_linear_vel": MAX_LINEAR_VEL,
            "max_angular_vel": MAX_ANGULAR_VEL,
            "motion_active": self._motion_active,
            "startup_error": self._startup_error,
        }

    def move(
        self,
        linear_x: float = 0.0,
        angular_z: float = 0.0,
        duration_s: float = 1.0,
    ) -> dict[str, object]:
        """Publish a Twist command for duration_s seconds, then stop."""
        if not self._started:
            raise RuntimeError("RobotMotionProvider is not running.")

        safe_linear = _clamp(float(linear_x), MAX_LINEAR_VEL)
        safe_angular = _clamp(float(angular_z), MAX_ANGULAR_VEL)
        safe_duration = min(max(0.0, float(duration_s)), MAX_LINEAR_DURATION_S)

        with self._lock:
            if self._motion_active:
                return {
                    "success": False,
                    "error": "Another motion command is already running.",
                }
            self._motion_active = True

        try:
            # Re-publish at 20 Hz for the full duration — satisfies the robot's cmd_vel watchdog
            # (most platforms stop the robot if no new cmd_vel arrives within ~0.5 s).
            end_time = time.monotonic() + safe_duration
            while True:
                self._publish_twist(safe_linear, safe_angular)
                remaining = end_time - time.monotonic()
                if remaining <= 0:
                    break
                time.sleep(min(0.05, remaining))
            self._publish_zero()
        finally:
            with self._lock:
                self._motion_active = False

        return {
            "success": True,
            "linear_x": safe_linear,
            "angular_z": safe_angular,
            "duration_s": safe_duration,
            "clamped": {
                "linear_x": safe_linear != float(linear_x),
                "angular_z": safe_angular != float(angular_z),
            },
            "topic": self._topic,
        }

    def move_distance(
        self,
        distance_m: float,
        speed_m_s: float = 0.15,
        pos_fn: Callable[[], tuple[float, float] | None] | None = None,
        tolerance_m: float = 0.02,
        allow_open_loop: bool = False,
        feedback_available_fn: Callable[[], bool] | None = None,
        feedback_timeout_s: float = 0.5,
    ) -> dict[str, object]:
        """Move forward (positive) or backward (negative) a fixed distance at a given speed."""
        if not self._started:
            raise RuntimeError("RobotMotionProvider is not running.")

        safe_speed = _clamp(abs(float(speed_m_s)), MAX_LINEAR_VEL)
        if safe_speed == 0.0:
            return {"success": False, "error": "Speed must be non-zero."}

        dist = float(distance_m)
        direction = 1.0 if dist >= 0.0 else -1.0
        linear_x = direction * safe_speed

        feedback_available = True if feedback_available_fn is None else bool(feedback_available_fn())
        if pos_fn is not None and feedback_available:
            initial_pos = pos_fn()
            if initial_pos is not None:
                return self._move_distance_closed_loop(
                    dist,
                    linear_x,
                    tolerance_m,
                    pos_fn,
                    initial_pos,
                    allow_open_loop=allow_open_loop,
                    feedback_available_fn=feedback_available_fn,
                    feedback_timeout_s=feedback_timeout_s,
                )

        if not allow_open_loop:
            return _motion_confirmation_required_payload("translation")

        duration_s = min(abs(dist) / safe_speed, MAX_LINEAR_DURATION_S)
        result = self.move(linear_x=linear_x, angular_z=0.0, duration_s=duration_s)
        result["mode"] = "open_loop_override"
        result["confirmed"] = False
        result["allow_open_loop"] = True
        return result

    def _move_distance_closed_loop(
        self,
        target_m: float,
        linear_x: float,
        tolerance_m: float,
        pos_fn: Callable[[], tuple[float, float] | None],
        initial_pos: tuple[float, float],
        allow_open_loop: bool,
        feedback_available_fn: Callable[[], bool] | None,
        feedback_timeout_s: float,
    ) -> dict[str, object]:
        import math

        with self._lock:
            if self._motion_active:
                return {"success": False, "error": "Another motion command is already running."}
            self._motion_active = True

        # Timeout: open-loop estimate with 50% headroom, capped at MAX_LINEAR_DURATION_S
        open_loop_est = abs(target_m) / abs(linear_x)
        timeout_s = min(open_loop_est * 1.5 + 1.0, MAX_LINEAR_DURATION_S)

        x0, y0 = initial_pos
        timed_out = False
        start_time = time.monotonic()
        last_feedback_at = start_time
        travelled_m = 0.0
        feedback_lost = False
        failed = False

        try:
            while True:
                self._publish_twist(linear_x, 0.0)  # re-publish at 20 Hz — satisfies cmd_vel watchdog
                time.sleep(0.05)

                feedback_available = True if feedback_available_fn is None else bool(feedback_available_fn())
                pos = pos_fn() if feedback_available else None
                if pos is None:
                    if time.monotonic() - last_feedback_at > feedback_timeout_s:
                        if not allow_open_loop:
                            failed = True
                            break
                        feedback_lost = True
                    if time.monotonic() - start_time > timeout_s:
                        timed_out = True
                        break
                    continue

                last_feedback_at = time.monotonic()
                x, y = pos
                travelled_m = math.sqrt((x - x0) ** 2 + (y - y0) ** 2)

                # Stop if within tolerance of target
                if travelled_m >= abs(target_m) - tolerance_m:
                    break

                if time.monotonic() - start_time > timeout_s:
                    timed_out = True
                    break

            self._publish_zero()
        finally:
            with self._lock:
                self._motion_active = False

        if failed:
            return {
                **_feedback_lost_payload("translation"),
                "mode": "closed_loop",
                "requested_distance_m": target_m,
                "actual_distance_m": round(travelled_m, 4),
                "linear_x": linear_x,
                "topic": self._topic,
            }
        if timed_out:
            return {
                "success": False,
                "error": "Timed out before the requested translation was confirmed.",
                "mode": "closed_loop" if not feedback_lost else "open_loop_override",
                "requested_distance_m": target_m,
                "actual_distance_m": round(travelled_m, 4),
                "timed_out": True,
                "confirmed": False,
                "linear_x": linear_x,
                "topic": self._topic,
            }
        return {
            "success": True,
            "mode": "closed_loop" if not feedback_lost else "open_loop_override",
            "requested_distance_m": target_m,
            "actual_distance_m": round(travelled_m, 4),
            "timed_out": False,
            "confirmed": not feedback_lost,
            "allow_open_loop": allow_open_loop,
            "linear_x": linear_x,
            "topic": self._topic,
        }

    def rotate_angle(
        self,
        angle_deg: float,
        speed_rad_s: float = 0.4,
        yaw_fn: Callable[[], float | None] | None = None,
        tolerance_deg: float = 3.0,
        allow_open_loop: bool = False,
        feedback_available_fn: Callable[[], bool] | None = None,
        feedback_timeout_s: float = 0.5,
    ) -> dict[str, object]:
        """Rotate in place by angle_deg degrees, using odometry feedback if available."""
        import math
        if not self._started:
            raise RuntimeError("RobotMotionProvider is not running.")

        safe_speed = _clamp(abs(float(speed_rad_s)), MAX_ANGULAR_VEL)
        if safe_speed == 0.0:
            return {"success": False, "error": "speed_rad_s must be non-zero."}

        target_deg = float(angle_deg)
        target_rad = math.radians(target_deg)
        direction = 1.0 if target_rad >= 0.0 else -1.0
        angular_z = direction * safe_speed
        tolerance_rad = math.radians(max(0.5, float(tolerance_deg)))

        feedback_available = True if feedback_available_fn is None else bool(feedback_available_fn())
        if yaw_fn is not None and feedback_available:
            initial_yaw = yaw_fn()
            if initial_yaw is not None:
                return self._rotate_closed_loop(
                    target_deg,
                    angular_z,
                    tolerance_rad,
                    yaw_fn,
                    initial_yaw,
                    allow_open_loop=allow_open_loop,
                    feedback_available_fn=feedback_available_fn,
                    feedback_timeout_s=feedback_timeout_s,
                )

        if not allow_open_loop:
            return _motion_confirmation_required_payload("rotation")

        duration_s = min(abs(target_rad) / safe_speed, MAX_ANGULAR_DURATION_S)
        result = self.move(linear_x=0.0, angular_z=angular_z, duration_s=duration_s)
        result["mode"] = "open_loop_override"
        result["confirmed"] = False
        result["allow_open_loop"] = True
        return result

    def _rotate_closed_loop(
        self,
        target_deg: float,
        angular_z: float,
        tolerance_rad: float,
        yaw_fn: Callable[[], float | None],
        initial_yaw: float,
        allow_open_loop: bool,
        feedback_available_fn: Callable[[], bool] | None,
        feedback_timeout_s: float,
    ) -> dict[str, object]:
        import math

        with self._lock:
            if self._motion_active:
                return {"success": False, "error": "Another motion command is already running."}
            self._motion_active = True

        # Timeout: open-loop estimate with 150% headroom, capped at MAX_ANGULAR_DURATION_S
        # Factor 2.5 tolerates robots that run ~2× slower than the commanded speed
        open_loop_est = abs(math.radians(target_deg)) / abs(angular_z)
        timeout_s = min(open_loop_est * 2.5 + 2.0, MAX_ANGULAR_DURATION_S)

        accumulated_rad = 0.0
        prev_yaw = initial_yaw
        timed_out = False
        start_time = time.monotonic()
        last_feedback_at = start_time
        feedback_lost = False
        failed = False

        try:
            while True:
                self._publish_twist(0.0, angular_z)  # re-publish at 20 Hz — satisfies cmd_vel watchdog
                time.sleep(0.05)

                feedback_available = True if feedback_available_fn is None else bool(feedback_available_fn())
                current_yaw = yaw_fn() if feedback_available else None
                if current_yaw is None:
                    if time.monotonic() - last_feedback_at > feedback_timeout_s:
                        if not allow_open_loop:
                            failed = True
                            break
                        feedback_lost = True
                    if time.monotonic() - start_time > timeout_s:
                        timed_out = True
                        break
                    continue

                last_feedback_at = time.monotonic()
                # Accumulate rotation, handling ±π wraparound at each step
                delta = _signed_angle_diff(current_yaw, prev_yaw)
                accumulated_rad += delta
                prev_yaw = current_yaw

                # Stop if within tolerance of target
                remaining = math.radians(target_deg) - accumulated_rad
                if abs(remaining) <= tolerance_rad:
                    break

                # Stop if overshot past tolerance
                if (target_deg > 0 and accumulated_rad > math.radians(target_deg) + tolerance_rad) or \
                   (target_deg < 0 and accumulated_rad < math.radians(target_deg) - tolerance_rad):
                    break

                if time.monotonic() - start_time > timeout_s:
                    timed_out = True
                    break

            self._publish_zero()
        finally:
            with self._lock:
                self._motion_active = False

        if failed:
            return {
                **_feedback_lost_payload("rotation"),
                "mode": "closed_loop",
                "requested_angle_deg": target_deg,
                "actual_angle_deg": round(math.degrees(accumulated_rad), 1),
                "angular_z": angular_z,
                "topic": self._topic,
            }
        if timed_out:
            return {
                "success": False,
                "error": "Timed out before the requested rotation was confirmed.",
                "mode": "closed_loop" if not feedback_lost else "open_loop_override",
                "requested_angle_deg": target_deg,
                "actual_angle_deg": round(math.degrees(accumulated_rad), 1),
                "timed_out": True,
                "confirmed": False,
                "angular_z": angular_z,
                "topic": self._topic,
            }
        return {
            "success": True,
            "mode": "closed_loop" if not feedback_lost else "open_loop_override",
            "requested_angle_deg": target_deg,
            "actual_angle_deg": round(math.degrees(accumulated_rad), 1),
            "timed_out": False,
            "confirmed": not feedback_lost,
            "allow_open_loop": allow_open_loop,
            "angular_z": angular_z,
            "topic": self._topic,
        }

    def stop(self) -> dict[str, object]:
        """Publish a zero-velocity Twist immediately."""
        if not self._started:
            raise RuntimeError("RobotMotionProvider is not running.")
        self._publish_zero()
        with self._lock:
            self._motion_active = False
        return {"success": True, "detail": "Zero velocity published."}

    def _publish_twist(self, linear_x: float, angular_z: float) -> None:
        msg = Twist()
        msg.linear.x = float(linear_x)
        msg.angular.z = float(angular_z)
        self._publisher.publish(msg)

    def _publish_zero(self) -> None:
        if self._publisher:
            self._publish_twist(0.0, 0.0)
