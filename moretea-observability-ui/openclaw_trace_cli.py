from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from copy import deepcopy
from datetime import datetime, timezone
from json import JSONDecoder
from typing import Any

TOOL_START_RE = re.compile(
    r"embedded run tool start: runId=(?P<run_id>\S+) tool=(?P<tool>\S+) toolCallId=(?P<tool_call_id>\S+)"
)
TOOL_END_RE = re.compile(
    r"embedded run tool end: runId=(?P<run_id>\S+) tool=(?P<tool>\S+) toolCallId=(?P<tool_call_id>\S+)"
)
SUBAGENT_WARN_RE = re.compile(
    r"subagent cleanup finalize failed \((?P<child_id>[^)]+)\): (?P<error>.+)"
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _extract_json_object(output: str) -> dict[str, Any]:
    decoder = JSONDecoder()
    best: dict[str, Any] | None = None
    best_end = -1
    for index, char in enumerate(output):
        if char != "{":
            continue
        try:
            candidate, end = decoder.raw_decode(output[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(candidate, dict) and index + end > best_end:
            best = candidate
            best_end = index + end
    if best is None:
        raise ValueError("Could not find a JSON object in OpenClaw output.")
    return best


def enrich_openclaw_output(output: str) -> dict[str, Any]:
    base = _extract_json_object(output)
    tool_executions: list[dict[str, Any]] = []
    timeline_events: list[dict[str, Any]] = []
    session_structure = {
        "main_session_id": base.get("meta", {}).get("agentMeta", {}).get("sessionId", "main"),
        "child_sessions": [],
        "note": "",
    }
    tools_by_id: dict[str, dict[str, Any]] = {}

    for raw_line in output.splitlines():
        line = raw_line.strip()
        timestamp = _utc_now()
        start_match = TOOL_START_RE.search(line)
        if start_match:
            tool_call_id = start_match.group("tool_call_id")
            tool_name = start_match.group("tool")
            tool = {
                "id": tool_call_id,
                "tool_name": tool_name,
                "tool_kind": "builtin" if not tool_name.startswith("moretea_robot_") else "mcp",
                "host_machine": "openclaw-pc",
                "status": "healthy",
                "started_at": timestamp,
                "ended_at": None,
                "duration_ms": None,
                "session_id": session_structure["main_session_id"],
                "parent_session_id": None,
                "child_session_id": None,
                "args_summary": None,
                "result_summary": None,
                "result_raw": None,
                "error": None,
                "summary": f"{tool_name} started.",
                "raw": {"log_line": line},
            }
            tools_by_id[tool_call_id] = tool
            tool_executions.append(tool)
            timeline_events.append(
                {
                    "id": f"{tool_call_id}-start",
                    "turn_id": session_structure["main_session_id"],
                    "machine_id": "openclaw-pc",
                    "service_id": "openclaw",
                    "type": "tool_call",
                    "status": "healthy",
                    "timestamp": timestamp,
                    "latency_ms": None,
                    "payload_summary": f"Called `{tool_name}`.",
                    "raw": {
                        "tool_execution_id": tool_call_id,
                        "tool_name": tool_name,
                        "tool_kind": tool["tool_kind"],
                        "session_id": session_structure["main_session_id"],
                    },
                }
            )
            continue

        end_match = TOOL_END_RE.search(line)
        if end_match:
            tool_call_id = end_match.group("tool_call_id")
            tool_name = end_match.group("tool")
            tool = tools_by_id.get(tool_call_id)
            if tool is None:
                tool = {
                    "id": tool_call_id,
                    "tool_name": tool_name,
                    "tool_kind": "builtin" if not tool_name.startswith("moretea_robot_") else "mcp",
                    "host_machine": "openclaw-pc",
                    "status": "healthy",
                    "started_at": timestamp,
                    "ended_at": None,
                    "duration_ms": None,
                    "session_id": session_structure["main_session_id"],
                    "parent_session_id": None,
                    "child_session_id": None,
                    "args_summary": None,
                    "result_summary": None,
                    "result_raw": None,
                    "error": None,
                    "summary": "",
                    "raw": {},
                }
                tools_by_id[tool_call_id] = tool
                tool_executions.append(tool)
            tool["ended_at"] = timestamp
            tool["result_summary"] = f"{tool_name} returned."
            tool["summary"] = tool["result_summary"]
            tool["raw"] = {"log_line": line}
            timeline_events.append(
                {
                    "id": f"{tool_call_id}-finish",
                    "turn_id": session_structure["main_session_id"],
                    "machine_id": "openclaw-pc",
                    "service_id": "openclaw",
                    "type": "tool_result",
                    "status": "healthy",
                    "timestamp": timestamp,
                    "latency_ms": None,
                    "payload_summary": f"`{tool_name}` returned.",
                    "raw": {
                        "tool_execution_id": tool_call_id,
                        "tool_name": tool_name,
                        "tool_kind": tool["tool_kind"],
                        "session_id": session_structure["main_session_id"],
                    },
                }
            )
            continue

        child_match = SUBAGENT_WARN_RE.search(line)
        if child_match:
            child_id = child_match.group("child_id")
            error = child_match.group("error")
            session_structure["child_sessions"].append(
                {
                    "id": child_id,
                    "role": "background action",
                    "status": "error",
                    "note": error,
                    "parent_session_id": session_structure["main_session_id"],
                }
            )
            session_structure["note"] = "A child session was spawned, but cleanup reported an error."
            timeline_events.append(
                {
                    "id": f"{child_id}-missing-result",
                    "turn_id": session_structure["main_session_id"],
                    "machine_id": "openclaw-pc",
                    "service_id": "openclaw",
                    "type": "child_session_missing_result",
                    "status": "error",
                    "timestamp": timestamp,
                    "latency_ms": None,
                    "payload_summary": error,
                    "raw": {
                        "child_session_id": child_id,
                        "parent_session_id": session_structure["main_session_id"],
                        "status": "error",
                        "message": error,
                    },
                }
            )

    enriched = deepcopy(base)
    enriched["tool_executions"] = tool_executions
    enriched["timeline_events"] = timeline_events
    enriched["session_structure"] = session_structure
    return enriched


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run OpenClaw and enrich its JSON output with tool/timeline/session trace fields.",
    )
    parser.add_argument("command", nargs=argparse.REMAINDER, help="Command to run after `--`.")
    args = parser.parse_args()

    command = args.command
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        parser.error("Provide the OpenClaw command after `--`.")

    result = subprocess.run(command, capture_output=True, text=True, check=False)
    combined = result.stdout
    if result.stderr:
        combined = f"{combined}\n{result.stderr}" if combined else result.stderr

    enriched = enrich_openclaw_output(combined)
    print(json.dumps(enriched, indent=2, sort_keys=True))
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
