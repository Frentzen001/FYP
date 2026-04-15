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
from uuid import uuid4

TOOL_START_RE = re.compile(
    r"embedded run tool start: runId=(?P<run_id>\S+) tool=(?P<tool>\S+) toolCallId=(?P<tool_call_id>\S+)"
)
TOOL_END_RE = re.compile(
    r"embedded run tool end: runId=(?P<run_id>\S+) tool=(?P<tool>\S+) toolCallId=(?P<tool_call_id>\S+)"
)
SUBAGENT_WARN_RE = re.compile(
    r"subagent cleanup finalize failed \((?P<child_id>[^)]+)\): (?P<error>.+)"
)
RUN_START_RE = re.compile(
    r"embedded run start: runId=(?P<run_id>\S+) sessionId=(?P<session_id>\S+) provider=(?P<provider>\S+) model=(?P<model>\S+)"
)
RUN_DONE_RE = re.compile(
    r"embedded run done: runId=(?P<run_id>\S+) sessionId=(?P<session_id>\S+) durationMs=(?P<duration_ms>\d+) aborted=(?P<aborted>\S+)"
)
RUN_FAILOVER_RE = re.compile(
    r"embedded run failover decision: runId=(?P<run_id>\S+) stage=(?P<stage>\S+) decision=(?P<decision>\S+) reason=(?P<reason>\S+)"
)
AGENT_WAIT_RE = re.compile(
    r"agent\.wait (?P<duration_ms>\d+)ms .* id=(?P<wait_id>\S+)"
)


class TraceParseError(ValueError):
    def __init__(self, message: str, *, command: list[str], stdout: str, stderr: str) -> None:
        super().__init__(message)
        self.command = command
        self.stdout = stdout
        self.stderr = stderr


def _summarize_stream(value: str, *, limit: int = 1200) -> str:
    text = value.strip()
    if not text:
        return "<empty>"
    if len(text) <= limit:
        return text
    return f"{text[:limit - 1]}..."


def _status_from_abort(value: str) -> str:
    return "error" if value.strip().lower() in {"1", "true", "yes", "on"} else "completed"


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
    child_by_run_id: dict[str, str] = {}
    child_by_session_id: dict[str, str] = {}
    pending_spawn_ids: list[str] = []

    def ensure_child_session(
        child_id: str,
        *,
        role: str = "background action",
        status: str = "spawned",
        note: str | None = None,
        parent_session_id: str | None = None,
    ) -> dict[str, Any]:
        current = next((item for item in session_structure["child_sessions"] if item.get("id") == child_id), None)
        if current is None:
            current = {
                "id": child_id,
                "role": role,
                "status": status,
                "note": note or "",
                "parent_session_id": parent_session_id or session_structure["main_session_id"],
                "last_message": None,
            }
            session_structure["child_sessions"].append(current)
        else:
            current["role"] = role or current.get("role", "background action")
            current["status"] = status or current.get("status", "spawned")
            if note:
                current["note"] = note
            if parent_session_id:
                current["parent_session_id"] = parent_session_id
        return current

    def replace_child_session_id(old_id: str, new_id: str) -> None:
        current = next((item for item in session_structure["child_sessions"] if item.get("id") == old_id), None)
        if current is None:
            return
        current["id"] = new_id
        for tool in tool_executions:
            if tool.get("child_session_id") == old_id:
                tool["child_session_id"] = new_id
            if tool.get("session_id") == old_id:
                tool["session_id"] = new_id
        for event in timeline_events:
            raw = event.get("raw") or {}
            if raw.get("child_session_id") == old_id:
                raw["child_session_id"] = new_id
            if raw.get("session_id") == old_id:
                raw["session_id"] = new_id

    def infer_latest_child_id() -> str | None:
        if pending_spawn_ids:
            return pending_spawn_ids[-1]
        if session_structure["child_sessions"]:
            return str(session_structure["child_sessions"][-1]["id"])
        return None

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
            if tool_name == "sessions_spawn":
                child_id = f"spawn:{tool_call_id}"
                tool["child_session_id"] = child_id
                ensure_child_session(
                    child_id,
                    status="spawned",
                    note="Child session spawned by sessions_spawn.",
                    parent_session_id=session_structure["main_session_id"],
                )
                pending_spawn_ids.append(child_id)
                timeline_events.append(
                    {
                        "id": f"{child_id}-spawned",
                        "turn_id": session_structure["main_session_id"],
                        "machine_id": "openclaw-pc",
                        "service_id": "openclaw",
                        "type": "child_session_spawned",
                        "status": "healthy",
                        "timestamp": timestamp,
                        "latency_ms": None,
                        "payload_summary": f"Spawned child session {child_id}.",
                        "raw": {
                            "child_session_id": child_id,
                            "parent_session_id": session_structure["main_session_id"],
                            "status": "spawned",
                            "role": "background action",
                            "tool_execution_id": tool_call_id,
                        },
                    }
                )
            continue

        run_start_match = RUN_START_RE.search(line)
        if run_start_match:
            run_id = run_start_match.group("run_id")
            session_id = run_start_match.group("session_id")
            if session_id != session_structure["main_session_id"]:
                child_id = child_by_session_id.get(session_id)
                if child_id is None:
                    inferred = infer_latest_child_id()
                    if inferred is not None and inferred.startswith("spawn:"):
                        replace_child_session_id(inferred, session_id)
                        try:
                            pending_spawn_ids[pending_spawn_ids.index(inferred)] = session_id
                        except ValueError:
                            pass
                        child_id = session_id
                    else:
                        child_id = inferred or f"child:{session_id}"
                child_by_run_id[run_id] = child_id
                child_by_session_id[session_id] = child_id
                ensure_child_session(
                    child_id,
                    status="running",
                    note=f"Child session {child_id} started running.",
                    parent_session_id=session_structure["main_session_id"],
                )
                timeline_events.append(
                    {
                        "id": f"{child_id}-started-{run_id}",
                        "turn_id": session_structure["main_session_id"],
                        "machine_id": "openclaw-pc",
                        "service_id": "openclaw",
                        "type": "child_session_started",
                        "status": "healthy",
                        "timestamp": timestamp,
                        "latency_ms": None,
                        "payload_summary": f"Child session {child_id} started.",
                        "raw": {
                            "child_session_id": child_id,
                            "parent_session_id": session_structure["main_session_id"],
                            "status": "running",
                            "role": "background action",
                            "run_id": run_id,
                            "session_id": session_id,
                            "provider": run_start_match.group("provider"),
                            "model": run_start_match.group("model"),
                        },
                    }
                )
            continue

        run_done_match = RUN_DONE_RE.search(line)
        if run_done_match:
            run_id = run_done_match.group("run_id")
            session_id = run_done_match.group("session_id")
            if session_id != session_structure["main_session_id"]:
                child_id = child_by_run_id.get(run_id) or child_by_session_id.get(session_id) or infer_latest_child_id()
                if child_id is not None:
                    status = _status_from_abort(run_done_match.group("aborted"))
                    ensure_child_session(
                        child_id,
                        status=status,
                        note=f"Child session {child_id} finished with status {status}.",
                        parent_session_id=session_structure["main_session_id"],
                    )
                    timeline_events.append(
                        {
                            "id": f"{child_id}-completed-{run_id}",
                            "turn_id": session_structure["main_session_id"],
                            "machine_id": "openclaw-pc",
                            "service_id": "openclaw",
                            "type": "child_session_completed" if status == "completed" else "child_session_errored",
                            "status": "healthy" if status == "completed" else "error",
                            "timestamp": timestamp,
                            "latency_ms": int(run_done_match.group("duration_ms")),
                            "payload_summary": f"Child session {child_id} finished.",
                            "raw": {
                                "child_session_id": child_id,
                                "parent_session_id": session_structure["main_session_id"],
                                "status": status,
                                "run_id": run_id,
                                "session_id": session_id,
                            },
                        }
                    )
            continue

        failover_match = RUN_FAILOVER_RE.search(line)
        if failover_match:
            child_id = child_by_run_id.get(failover_match.group("run_id")) or infer_latest_child_id()
            if child_id is not None:
                ensure_child_session(
                    child_id,
                    status="error",
                    note=f"Child session {child_id} hit failover: {failover_match.group('reason')}.",
                    parent_session_id=session_structure["main_session_id"],
                )
                timeline_events.append(
                    {
                        "id": f"{child_id}-errored-{failover_match.group('run_id')}",
                        "turn_id": session_structure["main_session_id"],
                        "machine_id": "openclaw-pc",
                        "service_id": "openclaw",
                        "type": "child_session_errored",
                        "status": "error",
                        "timestamp": timestamp,
                        "latency_ms": None,
                        "payload_summary": failover_match.group("reason"),
                        "raw": {
                            "child_session_id": child_id,
                            "parent_session_id": session_structure["main_session_id"],
                            "status": "error",
                            "run_id": failover_match.group("run_id"),
                            "reason": failover_match.group("reason"),
                            "decision": failover_match.group("decision"),
                            "stage": failover_match.group("stage"),
                        },
                    }
                )
            continue

        wait_match = AGENT_WAIT_RE.search(line)
        if wait_match:
            child_id = infer_latest_child_id()
            if child_id is not None:
                ensure_child_session(
                    child_id,
                    status="completed",
                    note=f"Child session {child_id} completed wait.",
                    parent_session_id=session_structure["main_session_id"],
                )
                timeline_events.append(
                    {
                        "id": f"{child_id}-wait-{wait_match.group('wait_id')}",
                        "turn_id": session_structure["main_session_id"],
                        "machine_id": "openclaw-pc",
                        "service_id": "openclaw",
                        "type": "child_session_completed",
                        "status": "healthy",
                        "timestamp": timestamp,
                        "latency_ms": int(wait_match.group("duration_ms")),
                        "payload_summary": f"Child session {child_id} completed wait.",
                        "raw": {
                            "child_session_id": child_id,
                            "parent_session_id": session_structure["main_session_id"],
                            "status": "completed",
                            "wait_id": wait_match.group("wait_id"),
                        },
                    }
                )
            continue

        child_match = SUBAGENT_WARN_RE.search(line)
        if child_match:
            child_id = child_match.group("child_id")
            error = child_match.group("error")
            ensure_child_session(
                child_id,
                status="error",
                note=error,
                parent_session_id=session_structure["main_session_id"],
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
    stdout = result.stdout or ""
    stderr = result.stderr or ""
    combined = stdout
    if stderr:
        combined = f"{combined}\n{stderr}" if combined else stderr

    try:
        enriched = enrich_openclaw_output(combined)
    except ValueError as exc:
        raise SystemExit(
            "\n".join(
                [
                    f"{exc}",
                    f"Command: {' '.join(command)}",
                    f"Exit code: {result.returncode}",
                    f"STDOUT summary: {_summarize_stream(stdout)}",
                    f"STDERR summary: {_summarize_stream(stderr)}",
                    "Recommendation: run the wrapped command directly and inspect its raw stdout/stderr.",
                    "For containerized OpenClaw, prefer: docker exec moretea-openclaw openclaw agent --local --session-id main --verbose on --message \"rotate 5 degrees\" --json",
                ]
            )
        )
    print(json.dumps(enriched, indent=2, sort_keys=True))
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
