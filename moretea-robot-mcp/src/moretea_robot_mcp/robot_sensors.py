from __future__ import annotations

import threading
from typing import Any

ODOM_TOPIC = "/odom"
BATTERY_TOPIC = "/battery_state"
SCAN_TOPIC = "/scan"

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
    from nav_msgs.msg import Odometry
    from sensor_msgs.msg import BatteryState, LaserScan

    SENSOR_MSGS_AVAILABLE = True
except ImportError:
    SENSOR_MSGS_AVAILABLE = False
    Odometry = object  # type: ignore[assignment,misc]
    BatteryState = object  # type: ignore[assignment,misc]
    LaserScan = object  # type: ignore[assignment,misc]


class RobotSensorProvider:
    """Read-only subscriber for odometry, battery state, and laser scan."""

    def __init__(
        self,
        odom_topic: str = ODOM_TOPIC,
        battery_topic: str = BATTERY_TOPIC,
        scan_topic: str = SCAN_TOPIC,
    ) -> None:
        self._odom_topic = odom_topic
        self._battery_topic = battery_topic
        self._scan_topic = scan_topic
        self._node: Any = None
        self._executor: Any = None
        self._spin_thread: threading.Thread | None = None
        self._started = False
        self._startup_error: str | None = None
        self._lock = threading.Lock()
        self._latest_odom: Any = None
        self._latest_battery: Any = None
        self._latest_scan: Any = None

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

        self._node = Node("moretea_robot_sensors")

        if SENSOR_MSGS_AVAILABLE:
            self._node.create_subscription(Odometry, self._odom_topic, self._on_odom, 10)
            self._node.create_subscription(BatteryState, self._battery_topic, self._on_battery, 10)
            self._node.create_subscription(LaserScan, self._scan_topic, self._on_scan, 10)

        self._executor = rclpy.executors.MultiThreadedExecutor()
        self._executor.add_node(self._node)
        self._spin_thread = threading.Thread(
            target=self._executor.spin,
            daemon=True,
            name="moretea_robot_sensors_spin",
        )
        self._spin_thread.start()
        self._started = True

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
                self._latest_odom = None
                self._latest_battery = None
                self._latest_scan = None
            self._started = False
            self._node = None
            self._executor = None
            self._spin_thread = None

    def health(self) -> dict[str, object]:
        with self._lock:
            return {
                "success": True,
                "ros_ready": bool(ROS2_AVAILABLE and self._started),
                "sensor_msgs_available": SENSOR_MSGS_AVAILABLE,
                "odom_received": self._latest_odom is not None,
                "battery_received": self._latest_battery is not None,
                "scan_received": self._latest_scan is not None,
                "topics": {
                    "odom": self._odom_topic,
                    "battery": self._battery_topic,
                    "scan": self._scan_topic,
                },
                "startup_error": self._startup_error,
            }

    def get_odometry(self) -> dict[str, object]:
        if not self._started:
            raise RuntimeError("RobotSensorProvider is not running.")
        with self._lock:
            msg = self._latest_odom
        if msg is None:
            return {"success": False, "error": "No odometry message received yet.", "topic": self._odom_topic}
        pose = msg.pose.pose
        twist = msg.twist.twist
        return {
            "success": True,
            "topic": self._odom_topic,
            "position": {
                "x": round(pose.position.x, 4),
                "y": round(pose.position.y, 4),
                "z": round(pose.position.z, 4),
            },
            "orientation": {
                "x": round(pose.orientation.x, 4),
                "y": round(pose.orientation.y, 4),
                "z": round(pose.orientation.z, 4),
                "w": round(pose.orientation.w, 4),
            },
            "velocity": {
                "linear_x": round(twist.linear.x, 4),
                "angular_z": round(twist.angular.z, 4),
            },
        }

    def get_position(self) -> tuple[float, float] | None:
        """Return current (x, y) position in metres from the latest odometry, or None."""
        with self._lock:
            msg = self._latest_odom
        if msg is None:
            return None
        p = msg.pose.pose.position
        return (p.x, p.y)

    def get_yaw(self) -> float | None:
        """Return current yaw in radians from the latest odometry quaternion, or None."""
        import math
        with self._lock:
            msg = self._latest_odom
        if msg is None:
            return None
        q = msg.pose.pose.orientation
        # Yaw from quaternion: atan2(2*(w*z + x*y), 1 - 2*(y^2 + z^2))
        siny_cosp = 2.0 * (q.w * q.z + q.x * q.y)
        cosy_cosp = 1.0 - 2.0 * (q.y * q.y + q.z * q.z)
        return math.atan2(siny_cosp, cosy_cosp)

    def get_battery(self) -> dict[str, object]:
        if not self._started:
            raise RuntimeError("RobotSensorProvider is not running.")
        with self._lock:
            msg = self._latest_battery
        if msg is None:
            return {"success": False, "error": "No battery message received yet.", "topic": self._battery_topic}
        percentage = getattr(msg, "percentage", None)
        voltage = getattr(msg, "voltage", None)
        return {
            "success": True,
            "topic": self._battery_topic,
            "percentage": round(float(percentage) * 100, 1) if percentage is not None else None,
            "voltage": round(float(voltage), 2) if voltage is not None else None,
            "power_supply_status": getattr(msg, "power_supply_status", None),
        }

    def get_laser_scan(self) -> dict[str, object]:
        if not self._started:
            raise RuntimeError("RobotSensorProvider is not running.")
        with self._lock:
            msg = self._latest_scan
        if msg is None:
            return {"success": False, "error": "No laser scan message received yet.", "topic": self._scan_topic}

        ranges = [r for r in msg.ranges if msg.range_min < r < msg.range_max]
        nearest_m = round(min(ranges), 3) if ranges else None
        farthest_m = round(max(ranges), 3) if ranges else None

        return {
            "success": True,
            "topic": self._scan_topic,
            "nearest_obstacle_m": nearest_m,
            "farthest_obstacle_m": farthest_m,
            "valid_readings": len(ranges),
            "range_min_m": msg.range_min,
            "range_max_m": msg.range_max,
        }

    def _on_odom(self, msg: Any) -> None:
        with self._lock:
            self._latest_odom = msg

    def _on_battery(self, msg: Any) -> None:
        with self._lock:
            self._latest_battery = msg

    def _on_scan(self, msg: Any) -> None:
        with self._lock:
            self._latest_scan = msg
