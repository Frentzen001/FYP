from __future__ import annotations

from moretea_observability_ui_test_support import make_store


def test_tool_events_project_into_rich_tool_execution() -> None:
    store = make_store()
    store.ingest_events(
        [
            {
                "id": "evt-1",
                "turn_id": "turn-1",
                "machine_id": "robot-pc",
                "service_id": "robot-control",
                "type": "tool_call",
                "status": "healthy",
                "timestamp": "2026-04-14T08:00:00+00:00",
                "payload_summary": "Rotation move requested.",
                "raw": {
                    "tool_execution_id": "tool-1",
                    "tool_name": "rotate_angle",
                    "tool_kind": "mcp",
                    "session_id": "child-1",
                    "parent_session_id": "main",
                    "child_session_id": "child-1",
                    "args_summary": "angle_deg=90.0",
                },
            },
            {
                "id": "evt-2",
                "turn_id": "turn-1",
                "machine_id": "robot-pc",
                "service_id": "robot-control",
                "type": "tool_result",
                "status": "healthy",
                "timestamp": "2026-04-14T08:00:01+00:00",
                "latency_ms": 1000,
                "payload_summary": "rotate_angle succeeded.",
                "raw": {
                    "tool_execution_id": "tool-1",
                    "tool_name": "rotate_angle",
                    "tool_kind": "mcp",
                    "session_id": "child-1",
                    "parent_session_id": "main",
                    "child_session_id": "child-1",
                    "result_summary": "rotate_angle succeeded.",
                    "result": {"success": True, "requested_angle_deg": 90.0},
                },
            },
        ]
    )

    turn = store.snapshot()["turns"][0]
    tool = turn["tool_executions"][0]

    assert tool["tool_name"] == "rotate_angle"
    assert tool["tool_kind"] == "mcp"
    assert tool["session_id"] == "child-1"
    assert tool["parent_session_id"] == "main"
    assert tool["child_session_id"] == "child-1"
    assert tool["args_summary"] == "angle_deg=90.0"
    assert tool["result_summary"] == "rotate_angle succeeded."
    assert tool["result_raw"] == {"success": True, "requested_angle_deg": 90.0}
    assert tool["duration_ms"] == 1000


def test_session_events_update_child_session_projection() -> None:
    store = make_store()
    store.ingest_events(
        [
            {
                "id": "evt-0",
                "turn_id": "turn-2",
                "machine_id": "robot-pc",
                "service_id": "robot-control",
                "type": "tool_result",
                "status": "healthy",
                "timestamp": "2026-04-14T07:59:59+00:00",
                "payload_summary": "rotate_angle succeeded.",
                "raw": {
                    "tool_execution_id": "tool-42",
                    "tool_name": "rotate_angle",
                    "tool_kind": "mcp",
                    "session_id": "child-42",
                    "parent_session_id": "main",
                    "child_session_id": "child-42",
                    "result_summary": "rotate_angle succeeded.",
                    "result": {"success": True},
                },
            },
            {
                "id": "evt-1",
                "turn_id": "turn-2",
                "machine_id": "openclaw-pc",
                "service_id": "openclaw",
                "type": "sessions_spawn",
                "status": "healthy",
                "timestamp": "2026-04-14T08:00:00+00:00",
                "payload_summary": "Spawned child session child-42.",
                "raw": {
                    "child_session_id": "child-42",
                    "parent_session_id": "main",
                    "role": "motion worker",
                    "status": "running",
                },
            },
            {
                "id": "evt-2",
                "turn_id": "turn-2",
                "machine_id": "openclaw-pc",
                "service_id": "openclaw",
                "type": "sessions_send",
                "status": "healthy",
                "timestamp": "2026-04-14T08:00:01+00:00",
                "payload_summary": "Child session reported back.",
                "raw": {
                    "child_session_id": "child-42",
                    "parent_session_id": "main",
                    "status": "reported",
                    "message": "rotate_angle returned success",
                },
            },
        ]
    )

    turn = store.snapshot()["turns"][0]
    child = turn["session_structure"]["child_sessions"][0]

    assert child["id"] == "child-42"
    assert child["status"] == "reported"
    assert child["parent_session_id"] == "main"
    assert "rotate_angle returned success" in child["note"]


def test_explicit_child_lifecycle_events_update_status() -> None:
    store = make_store()
    store.ingest_events(
        [
            {
                "id": "evt-1",
                "turn_id": "turn-3",
                "machine_id": "openclaw-pc",
                "service_id": "openclaw",
                "type": "child_session_spawned",
                "status": "healthy",
                "timestamp": "2026-04-14T08:00:00+00:00",
                "payload_summary": "Spawned child session child-99.",
                "raw": {
                    "child_session_id": "child-99",
                    "parent_session_id": "main",
                    "status": "spawned",
                },
            },
            {
                "id": "evt-2",
                "turn_id": "turn-3",
                "machine_id": "openclaw-pc",
                "service_id": "openclaw",
                "type": "child_session_started",
                "status": "healthy",
                "timestamp": "2026-04-14T08:00:01+00:00",
                "payload_summary": "Child session child-99 started.",
                "raw": {
                    "child_session_id": "child-99",
                    "parent_session_id": "main",
                    "status": "running",
                },
            },
            {
                "id": "evt-3",
                "turn_id": "turn-3",
                "machine_id": "openclaw-pc",
                "service_id": "openclaw",
                "type": "child_session_completed",
                "status": "healthy",
                "timestamp": "2026-04-14T08:00:02+00:00",
                "payload_summary": "Child session child-99 finished.",
                "raw": {
                    "child_session_id": "child-99",
                    "parent_session_id": "main",
                    "status": "completed",
                },
            },
        ]
    )

    turn = store.snapshot()["turns"][0]
    child = turn["session_structure"]["child_sessions"][0]

    assert child["id"] == "child-99"
    assert child["status"] == "completed"


def test_sessions_send_without_matching_tool_result_marks_child_warning() -> None:
    store = make_store()
    store.ingest_events(
        [
            {
                "id": "evt-1",
                "turn_id": "turn-4",
                "machine_id": "openclaw-pc",
                "service_id": "openclaw",
                "type": "sessions_spawn",
                "status": "healthy",
                "timestamp": "2026-04-14T08:00:00+00:00",
                "payload_summary": "Spawned child session child-77.",
                "raw": {
                    "child_session_id": "child-77",
                    "parent_session_id": "main",
                    "status": "spawned",
                },
            },
            {
                "id": "evt-2",
                "turn_id": "turn-4",
                "machine_id": "openclaw-pc",
                "service_id": "openclaw",
                "type": "sessions_send",
                "status": "healthy",
                "timestamp": "2026-04-14T08:00:01+00:00",
                "payload_summary": "Child session reported back.",
                "raw": {
                    "child_session_id": "child-77",
                    "parent_session_id": "main",
                    "status": "reported",
                    "message": "Rotation result: success",
                },
            },
        ]
    )

    turn = store.snapshot()["turns"][0]
    child = turn["session_structure"]["child_sessions"][0]
    warning = next(item for item in turn["timeline_events"] if item["type"] == "child_session_report_without_tool_result")

    assert child["status"] == "reported_without_tool"
    assert warning["raw"]["child_session_id"] == "child-77"
