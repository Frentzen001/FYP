from __future__ import annotations

from openclaw_trace_cli import enrich_openclaw_output


def test_enrich_openclaw_output_adds_trace_fields() -> None:
    output = """
[agent/embedded] embedded run tool start: runId=main tool=sessions_spawn toolCallId=call_123
[agent/embedded] embedded run tool end: runId=main tool=sessions_spawn toolCallId=call_123
{
  "payloads": [{"text": "I am rotating now.", "mediaUrl": null}],
  "meta": {"agentMeta": {"sessionId": "main"}}
}
[warn] subagent cleanup finalize failed (child-1): missing trace
"""
    enriched = enrich_openclaw_output(output)

    assert enriched["meta"]["agentMeta"]["sessionId"] == "main"
    assert enriched["tool_executions"][0]["tool_name"] == "sessions_spawn"
    assert enriched["timeline_events"][0]["type"] == "tool_call"
    assert enriched["timeline_events"][1]["type"] == "tool_result"
    assert enriched["timeline_events"][2]["type"] == "child_session_missing_result"
    assert enriched["session_structure"]["child_sessions"][0]["id"] == "child-1"
