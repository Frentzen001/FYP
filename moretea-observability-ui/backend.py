from __future__ import annotations

import asyncio
import json
import threading
from collections import deque
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

SNAPSHOT_PATH = Path("/tmp/moretea-observability-state.json")
MAX_TURNS = 200
MAX_TIMELINE_EVENTS = 2000
MAX_TOOL_EXECUTIONS = 200


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sorted_turns(turns: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(turns.values(), key=lambda item: item.get("started_at") or "", reverse=True)


def _timeline_sort_key(item: dict[str, Any]) -> tuple[str, str]:
    return (str(item.get("timestamp") or ""), str(item.get("id") or ""))


def _tool_sort_key(item: dict[str, Any]) -> tuple[str, str]:
    return (str(item.get("started_at") or ""), str(item.get("id") or ""))


def _truncate_text(value: Any, *, limit: int = 180) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return f"{text[:limit - 1]}..."


def _tool_status_for_event(event_type: str, status: str, raw: dict[str, Any]) -> str:
    if event_type in {"tool_error", "child_session_missing_result"}:
        return "error"
    if raw.get("error"):
        return "error"
    if isinstance(raw.get("result"), dict) and raw["result"].get("success") is False:
        return "error"
    return status or "healthy"


class ObservabilityStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._queues: set[asyncio.Queue[str]] = set()
        self._state = {
            "generated_at": _utc_now(),
            "current_turn_id": None,
            "latest_robot_snapshot": None,
            "machines": [],
            "links": [],
            "turns": [],
        }
        self._machine_index: dict[str, dict[str, Any]] = {}
        self._link_index: dict[str, dict[str, Any]] = {}
        self._turn_index: dict[str, dict[str, Any]] = {}
        self._timeline_events: deque[dict[str, Any]] = deque(maxlen=MAX_TIMELINE_EVENTS)
        self._load_snapshot()

    def _load_snapshot(self) -> None:
        if not SNAPSHOT_PATH.exists():
            return
        try:
            raw = json.loads(SNAPSHOT_PATH.read_text())
        except Exception:
            return
        with self._lock:
            self._state = raw
            self._machine_index = {
                item["id"]: deepcopy(item) for item in raw.get("machines", []) if item.get("id")
            }
            self._link_index = {
                item["id"]: deepcopy(item) for item in raw.get("links", []) if item.get("id")
            }
            self._turn_index = {
                item["id"]: deepcopy(item) for item in raw.get("turns", []) if item.get("id")
            }
            timeline: list[dict[str, Any]] = []
            for turn in self._turn_index.values():
                timeline.extend(turn.get("timeline_events", []))
            timeline.sort(key=_timeline_sort_key)
            self._timeline_events = deque(timeline[-MAX_TIMELINE_EVENTS:], maxlen=MAX_TIMELINE_EVENTS)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            self._refresh_state_locked()
            return deepcopy(self._state)

    async def subscribe(self) -> asyncio.Queue[str]:
        queue: asyncio.Queue[str] = asyncio.Queue()
        self._queues.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[str]) -> None:
        self._queues.discard(queue)

    def ingest_events(self, events: list[dict[str, Any]]) -> None:
        if not isinstance(events, list):
            raise HTTPException(status_code=400, detail="events must be a list")
        envelopes: list[dict[str, Any]] = []
        with self._lock:
            for event in events:
                normalized = self._normalize_event(event)
                self._apply_event_locked(normalized)
                envelopes.append({"kind": "event", "payload": normalized})
            self._refresh_state_locked()
            self._persist_locked()
        for envelope in envelopes:
            self._publish(envelope)

    def ingest_heartbeats(self, payload: dict[str, Any]) -> None:
        envelopes: list[dict[str, Any]] = []
        machine = payload.get("machine")
        services = payload.get("services", [])
        links = payload.get("links", [])
        with self._lock:
            if isinstance(machine, dict) and machine.get("id"):
                current = self._machine_index.get(machine["id"], {"services": []})
                current.update(machine)
                current.setdefault("services", [])
                self._machine_index[machine["id"]] = current
                envelopes.append({"kind": "machine", "payload": deepcopy(current)})
            for service in services:
                machine_id = service.get("machine_id")
                service_id = service.get("id")
                if not machine_id or not service_id:
                    continue
                target_machine = self._machine_index.setdefault(
                    machine_id,
                    {"id": machine_id, "name": machine_id, "summary": "", "health": "warning", "services": []},
                )
                target_machine.setdefault("services", [])
                existing = next(
                    (item for item in target_machine["services"] if item.get("id") == service_id),
                    None,
                )
                if existing is None:
                    target_machine["services"].append(deepcopy(service))
                else:
                    existing.update(service)
                envelopes.append({"kind": "service", "payload": deepcopy(service)})
            for link in links:
                if not link.get("id"):
                    continue
                current = self._link_index.get(link["id"], {})
                current.update(link)
                self._link_index[link["id"]] = current
                envelopes.append({"kind": "link", "payload": deepcopy(current)})
            self._refresh_state_locked()
            self._persist_locked()
        for envelope in envelopes:
            self._publish(envelope)

    def _normalize_event(self, event: dict[str, Any]) -> dict[str, Any]:
        timestamp = event.get("timestamp") or _utc_now()
        normalized = {
            "id": event.get("id") or f"evt-{timestamp}",
            "turn_id": event.get("turn_id"),
            "machine_id": event.get("machine_id"),
            "service_id": event.get("service_id"),
            "type": event.get("type", "unknown"),
            "status": event.get("status", "healthy"),
            "timestamp": timestamp,
            "latency_ms": event.get("latency_ms"),
            "payload_summary": event.get("payload_summary", ""),
            "raw": event.get("raw", {}),
        }
        return normalized

    def _apply_event_locked(self, event: dict[str, Any]) -> None:
        turn_id = event.get("turn_id")
        event_type = str(event.get("type"))
        if not turn_id and event_type.startswith("robot_"):
            turn_id = self._state.get("current_turn_id")
            event["turn_id"] = turn_id
        if turn_id:
            turn = self._get_or_create_turn_locked(turn_id, started_at=event.get("timestamp"))
            turn.setdefault("timeline_events", [])
            turn["timeline_events"].append(event)
            turn["timeline_events"] = sorted(turn["timeline_events"], key=_timeline_sort_key)[-MAX_TIMELINE_EVENTS:]
            self._apply_turn_projection_locked(turn, event)
            self._state["current_turn_id"] = turn_id
        self._timeline_events.append(event)

    def _get_or_create_turn_locked(self, turn_id: str, *, started_at: str | None = None) -> dict[str, Any]:
        turn = self._turn_index.get(turn_id)
        if turn is None:
            turn = {
                "id": turn_id,
                "started_at": started_at or _utc_now(),
                "title": "Live interaction",
                "transcript": None,
                "attention_decision": None,
                "openclaw_response": None,
                "session_structure": {
                    "main_session_id": "main",
                    "child_sessions": [],
                    "note": "",
                },
                "tool_executions": [],
                "robot_action_state": None,
                "robot_readiness": None,
                "personalization": {
                    "recognized_faces": [],
                    "register_face_offered": False,
                    "memory_activity": [],
                },
                "timeline_events": [],
            }
            self._turn_index[turn_id] = turn
        return turn

    def _apply_turn_projection_locked(self, turn: dict[str, Any], event: dict[str, Any]) -> None:
        event_type = str(event.get("type"))
        raw = event.get("raw") or {}
        summary = event.get("payload_summary") or ""
        if event_type == "transcript_ready":
            turn["transcript"] = {
                "text": raw.get("text") or summary,
                "source_service_id": event.get("service_id"),
                "latency_ms": event.get("latency_ms"),
            }
            if not turn.get("title") or turn["title"] == "Live interaction":
                turn["title"] = raw.get("text") or summary or "Live interaction"
        elif event_type == "attention_decision":
            turn["attention_decision"] = {
                "state": raw.get("state"),
                "classification": raw.get("classification"),
                "handled": raw.get("handled"),
                "reason": summary,
            }
        elif event_type == "openclaw_response_ready":
            turn["openclaw_response"] = {
                "text": raw.get("text") or summary,
                "latency_ms": event.get("latency_ms"),
                "source_service_id": event.get("service_id"),
            }
        elif event_type in {"tool_started", "tool_finished", "tool_call", "tool_result", "tool_error"}:
            self._apply_tool_event_locked(turn, event)
        elif event_type == "robot_snapshot":
            turn["robot_readiness"] = raw.get("robot_readiness")
            turn["robot_action_state"] = raw.get("robot_action_state")
            if raw.get("personalization"):
                turn["personalization"] = raw["personalization"]
            self._state["latest_robot_snapshot"] = raw
        elif event_type == "face_check":
            personalization = turn.setdefault(
                "personalization",
                {"recognized_faces": [], "register_face_offered": False, "memory_activity": []},
            )
            personalization["recognized_faces"] = raw.get("recognized_faces", [])
        elif event_type == "memory_activity":
            personalization = turn.setdefault(
                "personalization",
                {"recognized_faces": [], "register_face_offered": False, "memory_activity": []},
            )
            activity = raw.get("activity")
            if activity:
                personalization.setdefault("memory_activity", []).append(activity)
        elif event_type == "session_activity":
            self._apply_session_event_locked(turn, event)
        elif event_type in {"sessions_spawn", "sessions_send", "child_session_missing_result"}:
            self._apply_session_event_locked(turn, event)

    def _apply_tool_event_locked(self, turn: dict[str, Any], event: dict[str, Any]) -> None:
        event_type = str(event.get("type"))
        raw = event.get("raw") or {}
        execution_id = raw.get("tool_execution_id")
        tool_name = raw.get("tool_name")
        if not execution_id or not tool_name:
            return
        tool = next(
            (item for item in turn["tool_executions"] if item.get("id") == execution_id),
            None,
        )
        if tool is None:
            tool = {
                "id": execution_id,
                "tool_name": tool_name,
                "tool_kind": raw.get("tool_kind", "mcp"),
                "host_machine": event.get("machine_id"),
                "status": "healthy",
                "started_at": event.get("timestamp"),
                "ended_at": None,
                "duration_ms": None,
                "session_id": raw.get("session_id"),
                "parent_session_id": raw.get("parent_session_id"),
                "child_session_id": raw.get("child_session_id"),
                "args_summary": raw.get("args_summary"),
                "result_summary": None,
                "result_raw": None,
                "error": None,
                "summary": "",
                "raw": {},
            }
            turn["tool_executions"].append(tool)

        tool["tool_kind"] = raw.get("tool_kind", tool.get("tool_kind", "mcp"))
        tool["host_machine"] = event.get("machine_id") or tool.get("host_machine")
        tool["session_id"] = raw.get("session_id", tool.get("session_id"))
        tool["parent_session_id"] = raw.get("parent_session_id", tool.get("parent_session_id"))
        tool["child_session_id"] = raw.get("child_session_id", tool.get("child_session_id"))
        tool["summary"] = event.get("payload_summary") or tool.get("summary") or ""
        tool["status"] = _tool_status_for_event(event_type, str(event.get("status") or tool.get("status") or "healthy"), raw)

        if raw.get("args_summary"):
            tool["args_summary"] = raw["args_summary"]
        if event_type in {"tool_started", "tool_call"}:
            tool["started_at"] = event.get("timestamp") or tool.get("started_at")
        else:
            tool["ended_at"] = event.get("timestamp") or tool.get("ended_at")
            tool["duration_ms"] = event.get("latency_ms", tool.get("duration_ms"))
            tool["result_summary"] = raw.get("result_summary") or tool.get("result_summary") or event.get("payload_summary") or ""
            tool["result_raw"] = deepcopy(raw.get("result")) if "result" in raw else tool.get("result_raw")
            tool["error"] = raw.get("error", tool.get("error"))

        tool["raw"] = deepcopy(raw)
        turn["tool_executions"] = sorted(
            turn["tool_executions"],
            key=_tool_sort_key,
        )[-MAX_TOOL_EXECUTIONS:]

        if tool_name == "sessions_spawn" or event_type == "sessions_spawn":
            self._apply_session_event_locked(
                turn,
                {
                    "type": "sessions_spawn",
                    "payload_summary": tool.get("result_summary") or tool.get("summary") or "Child session spawned.",
                    "raw": {
                        "child_session_id": tool.get("child_session_id"),
                        "parent_session_id": tool.get("session_id") or tool.get("parent_session_id"),
                        "status": "running",
                        "role": raw.get("child_role", "background action"),
                    },
                },
            )

    def _apply_session_event_locked(self, turn: dict[str, Any], event: dict[str, Any]) -> None:
        event_type = str(event.get("type"))
        raw = event.get("raw") or {}
        summary = event.get("payload_summary") or ""
        session = turn.setdefault(
            "session_structure",
            {"main_session_id": "main", "child_sessions": [], "note": ""},
        )
        session["main_session_id"] = raw.get("main_session_id", session.get("main_session_id", "main"))
        if summary:
            session["note"] = summary
        child_id = raw.get("child_session_id")
        if not child_id:
            return
        current = next((item for item in session["child_sessions"] if item.get("id") == child_id), None)
        payload = {
            "id": child_id,
            "role": raw.get("role", "background action"),
            "status": raw.get("status", "running"),
            "note": summary,
            "parent_session_id": raw.get("parent_session_id"),
            "last_message": raw.get("message"),
        }
        if event_type == "sessions_send":
            payload["status"] = raw.get("status", "reported")
            if raw.get("message"):
                payload["note"] = _truncate_text(raw["message"])
        elif event_type == "child_session_missing_result":
            payload["status"] = "error"
        if current is None:
            session["child_sessions"].append(payload)
        else:
            current.update({key: value for key, value in payload.items() if value is not None})

    def _refresh_state_locked(self) -> None:
        turns = _sorted_turns(self._turn_index)
        if len(turns) > MAX_TURNS:
            keep_ids = {item["id"] for item in turns[:MAX_TURNS]}
            self._turn_index = {key: value for key, value in self._turn_index.items() if key in keep_ids}
            turns = turns[:MAX_TURNS]
        self._state["generated_at"] = _utc_now()
        self._state["machines"] = sorted(self._machine_index.values(), key=lambda item: item.get("name", ""))
        self._state["links"] = sorted(self._link_index.values(), key=lambda item: item.get("name", ""))
        self._state["turns"] = turns

    def _persist_locked(self) -> None:
        SNAPSHOT_PATH.write_text(json.dumps(self._state, indent=2, sort_keys=True))

    def _publish(self, payload: dict[str, Any]) -> None:
        if not self._queues:
            return
        message = f"data: {json.dumps(payload, sort_keys=True)}\n\n"
        stale: list[asyncio.Queue[str]] = []
        for queue in list(self._queues):
            try:
                queue.put_nowait(message)
            except Exception:
                stale.append(queue)
        for queue in stale:
            self._queues.discard(queue)


store = ObservabilityStore()
app = FastAPI(title="MoreTea Observability Aggregator")


@app.get("/api/health")
async def health() -> dict[str, Any]:
    return {"ok": True, "generated_at": _utc_now()}


@app.get("/api/state")
async def get_state() -> dict[str, Any]:
    return store.snapshot()


@app.post("/api/ingest/events")
async def ingest_events(payload: dict[str, Any]) -> JSONResponse:
    events = payload.get("events", [])
    store.ingest_events(events)
    return JSONResponse({"ok": True, "count": len(events)})


@app.post("/api/ingest/heartbeats")
async def ingest_heartbeats(payload: dict[str, Any]) -> JSONResponse:
    store.ingest_heartbeats(payload)
    return JSONResponse({"ok": True})


@app.get("/api/events/stream")
async def stream_events() -> StreamingResponse:
    async def event_stream() -> Any:
        queue = await store.subscribe()
        try:
            yield f"data: {json.dumps({'kind': 'snapshot_ready'})}\n\n"
            while True:
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=15.0)
                except asyncio.TimeoutError:
                    yield f"data: {json.dumps({'kind': 'ping', 'generated_at': _utc_now()})}\n\n"
                    continue
                yield message
        finally:
            store.unsubscribe(queue)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


STATIC_ROOT = Path(__file__).resolve().parent
app.mount("/", StaticFiles(directory=STATIC_ROOT, html=True), name="static")


def main() -> None:
    host = "127.0.0.1"
    port = 4173
    uvicorn.run("backend:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
