from moretea_robot_mcp.ros_eye_publisher import EyeExpressionPublisher, ROS2_AVAILABLE


def test_health_reports_topic_and_emotions_when_not_started() -> None:
    publisher = EyeExpressionPublisher()

    health = publisher.health()

    assert health["success"] is True
    assert health["topic"] == "/eye_expression"
    assert "happy" in health["supported_emotions"]
    assert health["ros_ready"] is False


def test_publish_emotion_requires_started_publisher() -> None:
    publisher = EyeExpressionPublisher()

    try:
        publisher.publish_emotion("happy")
    except RuntimeError as exc:
        assert "not running" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Expected RuntimeError when publisher is not started.")


def test_ros_import_guard_is_explicit() -> None:
    assert isinstance(ROS2_AVAILABLE, bool)
