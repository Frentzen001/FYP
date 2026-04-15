from __future__ import annotations

from types import SimpleNamespace

from moretea_robot_mcp import server
from moretea_robot_mcp.robot_motion import RobotMotionProvider


class FakeProvider:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def health(self) -> dict[str, object]:
        return dict(self.payload)


class FakeMotionProvider(FakeProvider):
    def __init__(self) -> None:
        super().__init__(
            {
                "success": True,
                "ros_ready": True,
                "topic": "/cmd_vel",
                "max_linear_vel": 0.4,
                "max_angular_vel": 0.8,
                "motion_active": False,
                "startup_error": None,
            }
        )

    def stop(self) -> dict[str, object]:
        return {"success": True}


class FakeSensorProvider(FakeProvider):
    def __init__(self, *, odom_received: bool, odom_fresh: bool, odom_age_s: float | None) -> None:
        super().__init__(
            {
                "success": True,
                "ros_ready": True,
                "sensor_msgs_available": True,
                "odom_received": odom_received,
                "odom_fresh": odom_fresh,
                "odom_age_s": odom_age_s,
                "odom_stale_after_s": 1.0,
                "battery_received": False,
                "scan_received": False,
                "topics": {
                    "odom": "/odom",
                    "battery": "/battery_state",
                    "scan": "/scan",
                },
                "startup_error": None,
            }
        )

    def has_fresh_odometry(self) -> bool:
        return bool(self.payload["odom_fresh"])

    def get_position(self) -> tuple[float, float] | None:
        return (0.0, 0.0) if self.payload["odom_received"] else None

    def get_yaw(self) -> float | None:
        return 0.0 if self.payload["odom_received"] else None


def _ctx(*, motion: FakeMotionProvider | None = None, sensors: FakeSensorProvider | None = None):
    noop = FakeProvider({"success": True, "ros_ready": True})
    app = server.AppContext(
        publisher=noop,
        camera=noop,
        face_recognition=noop,
        face_registration=noop,
        navigation=noop,
        tour_navigation=noop,
        motion=motion or FakeMotionProvider(),
        sensors=sensors or FakeSensorProvider(odom_received=True, odom_fresh=True, odom_age_s=0.1),
        tour_stops=(),
    )
    return SimpleNamespace(request_context=SimpleNamespace(lifespan_context=app))


def test_health_reports_motion_not_confirmable_without_odometry() -> None:
    payload = server.health(
        _ctx(sensors=FakeSensorProvider(odom_received=False, odom_fresh=False, odom_age_s=None))
    )

    assert payload["motion_node_ready"] is True
    assert payload["odom_received"] is False
    assert payload["cmd_vel_publishable"] is True
    assert payload["motion_confirmable"] is False


def test_health_reports_motion_not_confirmable_with_stale_odometry() -> None:
    payload = server.health(
        _ctx(sensors=FakeSensorProvider(odom_received=True, odom_fresh=False, odom_age_s=2.5))
    )

    assert payload["odom_received"] is True
    assert payload["motion_confirmable"] is False
    assert payload["sensors"]["odom_fresh"] is False


def test_move_distance_refuses_unconfirmed_open_loop_by_default() -> None:
    provider = RobotMotionProvider()
    provider._started = True

    payload = provider.move_distance(distance_m=1.0, pos_fn=None)

    assert payload["success"] is False
    assert payload["requires_confirmation"] is True
    assert "allow_open_loop=True" in str(payload["error"])


def test_rotate_angle_refuses_unconfirmed_open_loop_by_default() -> None:
    provider = RobotMotionProvider()
    provider._started = True

    payload = provider.rotate_angle(angle_deg=90.0, yaw_fn=None)

    assert payload["success"] is False
    assert payload["requires_confirmation"] is True
    assert "allow_open_loop=True" in str(payload["error"])
