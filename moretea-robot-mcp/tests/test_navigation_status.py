from types import SimpleNamespace
from unittest.mock import patch

import moretea_robot_mcp.navigation_status as navigation_status
from moretea_robot_mcp.navigation_status import (
    NavigationSnapshot,
    NavigationStatusProvider,
    build_navigation_status,
    format_navigation_status_text,
)


EXPECTED_KEYS = {
    "success",
    "available",
    "is_navigating",
    "distance_remaining_m",
    "recovery_count",
    "replan_count",
    "last_event_note",
    "status_text",
}


def test_status_contract_is_stable_when_provider_is_idle() -> None:
    provider = NavigationStatusProvider()

    status = provider.status()

    assert set(status.keys()) == EXPECTED_KEYS
    assert status["success"] is True
    assert status["available"] is False
    assert status["is_navigating"] is False
    assert status["distance_remaining_m"] is None
    assert status["status_text"] == "Navigation is unavailable."


def test_format_navigation_status_text_matches_expected_messages() -> None:
    assert format_navigation_status_text(False, False, None) == "Navigation is unavailable."
    assert format_navigation_status_text(True, False, None) == "The robot is not currently navigating."
    assert (
        format_navigation_status_text(True, True, None)
        == "The robot is navigating, but distance feedback is not available yet."
    )
    assert format_navigation_status_text(True, True, 2.34) == "Approximately 2.3 metres remain."


def test_build_navigation_status_preserves_fields_and_formats_distance() -> None:
    status = build_navigation_status(
        NavigationSnapshot(
            success=True,
            available=True,
            is_navigating=True,
            distance_remaining_m=1.26,
            recovery_count=2,
            replan_count=1,
            last_event_note="I am taking a slightly different route to stay safe.",
        )
    )

    assert set(status.keys()) == EXPECTED_KEYS
    assert status["available"] is True
    assert status["is_navigating"] is True
    assert status["distance_remaining_m"] == 1.26
    assert status["recovery_count"] == 2
    assert status["replan_count"] == 1
    assert status["last_event_note"] == "I am taking a slightly different route to stay safe."
    assert status["status_text"] == "Approximately 1.3 metres remain."


def test_provider_reports_active_navigation_when_feedback_arrives() -> None:
    provider = NavigationStatusProvider()
    provider._started = True

    feedback = SimpleNamespace(
        feedback=SimpleNamespace(
            distance_remaining=0.8,
            number_of_recoveries=1,
            number_of_replans=0,
        )
    )

    with patch.object(navigation_status, "NAV2_STATUS_AVAILABLE", True):
        provider._on_feedback(feedback)
        status = provider.status()

    assert status["available"] is True
    assert status["is_navigating"] is True
    assert status["distance_remaining_m"] == 0.8
    assert status["recovery_count"] == 1
    assert status["replan_count"] == 0
    assert status["last_event_note"] == "I am taking a moment to recover around an obstacle."
    assert status["status_text"] == "Approximately 0.8 metres remain."
