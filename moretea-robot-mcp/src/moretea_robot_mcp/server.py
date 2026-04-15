from __future__ import annotations

import ipaddress
import os
import threading
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone

import uvicorn
from starlette.responses import Response
from starlette.types import ASGIApp, Receive, Scope, Send
from uuid import uuid4

from .camera_capture import CAMERA_TOPIC, CAMERA_TOPIC_KIND, CameraCaptureProvider
from .face_registration import FACE_DB_PATH, FACE_REGISTRATION_SERVICE, FaceRegistrationProvider
from .face_recognition_status import FACE_RECOGNITION_TOPIC, FaceRecognitionStatusProvider
from .navigation_status import NavigationStatusProvider
from .observability import RobotObservabilityReporter
from .robot_motion import CMD_VEL_TOPIC, RobotMotionProvider
from .robot_sensors import BATTERY_TOPIC, ODOM_TOPIC, SCAN_TOPIC, RobotSensorProvider
from .ros_eye_publisher import EyeExpressionPublisher
from .tour_navigation import TourNavigationExecutor
from .tour_stops import TourStop, load_tour_stops, serialize_stop

try:
    from mcp.server.fastmcp import Context, FastMCP
    from mcp.server.session import ServerSession
    from mcp.types import ImageContent
except ImportError:  # pragma: no cover - lightweight test fallback
    class ServerSession:  # type: ignore[no-redef]
        pass

    class Context:  # type: ignore[no-redef]
        def __class_getitem__(cls, _item: object) -> type["Context"]:
            return cls

    class FastMCP:  # type: ignore[no-redef]
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            return

        def tool(self) -> object:
            def decorator(func: object) -> object:
                return func

            return decorator

    ImageContent = None  # type: ignore[assignment,misc]


@dataclass
class AppContext:
    publisher: EyeExpressionPublisher
    camera: CameraCaptureProvider
    face_recognition: FaceRecognitionStatusProvider
    face_registration: FaceRegistrationProvider
    navigation: NavigationStatusProvider
    tour_navigation: TourNavigationExecutor
    motion: RobotMotionProvider
    sensors: RobotSensorProvider
    tour_stops: tuple[TourStop, ...]
    observability: RobotObservabilityReporter | None = None
    publisher_start_error: str | None = None
    camera_start_error: str | None = None
    face_recognition_start_error: str | None = None
    face_registration_start_error: str | None = None
    navigation_start_error: str | None = None
    tour_navigation_start_error: str | None = None
    motion_start_error: str | None = None
    sensors_start_error: str | None = None
    tour_stops_error: str | None = None


_ctx_singleton: AppContext | None = None
_ctx_singleton_lock = threading.Lock()
DEDUP_TTL_S = 30.0
_motion_dedup_cache: dict[str, tuple[dict[str, object], float]] = {}
_motion_dedup_lock = threading.Lock()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _truncate_text(value: object, *, limit: int = 180) -> str:
    text = str(value).strip()
    if len(text) <= limit:
        return text
    return f"{text[:limit - 1]}..."


def _summarize_args(**kwargs: object) -> str:
    parts: list[str] = []
    for key, value in kwargs.items():
        if value is None:
            continue
        parts.append(f"{key}={value}")
    return _truncate_text(", ".join(parts) or "no arguments")


def _summarize_result(tool_name: str, result: object) -> str:
    if isinstance(result, dict):
        if result.get("success") is False:
            return _truncate_text(result.get("error") or f"{tool_name} failed.")
        if tool_name == "health":
            if result.get("motion_confirmable"):
                return "Robot is ready and motion is confirmable."
            return "Robot health returned, but motion is not confirmable."
        if tool_name == "navigate_to_stop":
            status = result.get("status")
            event = result.get("event")
            if event:
                return _truncate_text(f"Navigation reported {event}.")
            if status:
                return _truncate_text(f"Navigation status is {status}.")
        if "detail" in result and result.get("detail"):
            return _truncate_text(result["detail"])
        if "message" in result and result.get("message"):
            return _truncate_text(result["message"])
        return _truncate_text(f"{tool_name} succeeded.")
    return _truncate_text(f"{tool_name} completed.")


def _request_value(source: object, key: str) -> object:
    if source is None:
        return None
    if isinstance(source, dict):
        return source.get(key)
    return getattr(source, key, None)


def _request_correlation(ctx: Context[ServerSession, AppContext]) -> dict[str, str | None]:
    request_context = getattr(ctx, "request_context", None)
    meta = getattr(request_context, "meta", None)
    request = getattr(request_context, "request", None)

    def _first_non_empty(*values: object) -> str | None:
        for value in values:
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    request_headers = getattr(request, "headers", None)
    session_id = _first_non_empty(
        _request_value(meta, "session_id"),
        _request_value(meta, "child_session_id"),
        _request_value(meta, "sessionId"),
        _request_value(meta, "childSessionId"),
        _request_value(request_headers, "x-openclaw-session-id"),
        _request_value(request_headers, "x-openclaw-child-session-id"),
    )
    parent_session_id = _first_non_empty(
        _request_value(meta, "parent_session_id"),
        _request_value(meta, "parentSessionId"),
        _request_value(request_headers, "x-openclaw-parent-session-id"),
    )
    turn_id = _first_non_empty(
        _request_value(meta, "turn_id"),
        _request_value(meta, "turnId"),
        _request_value(request_headers, "x-openclaw-turn-id"),
    )
    return {
        "session_id": session_id,
        "parent_session_id": parent_session_id,
        "turn_id": turn_id,
    }


def _normalize_motion_arg(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return format(value, ".6f")
    return str(value)


def _motion_dedup_key(turn_id: str | None, tool_name: str, **kwargs: object) -> str | None:
    if not turn_id:
        return None
    parts = [turn_id, tool_name]
    for key in sorted(kwargs):
        parts.append(f"{key}={_normalize_motion_arg(kwargs[key])}")
    return ":".join(parts)


def _prune_motion_dedup_cache(now: float) -> None:
    expired = [
        key for key, (_, stored_at) in _motion_dedup_cache.items() if now - stored_at >= DEDUP_TTL_S
    ]
    for key in expired:
        _motion_dedup_cache.pop(key, None)


def _check_motion_dedup(dedup_key: str | None) -> dict[str, object] | None:
    if dedup_key is None:
        return None
    now = time.monotonic()
    with _motion_dedup_lock:
        _prune_motion_dedup_cache(now)
        cached = _motion_dedup_cache.get(dedup_key)
        if cached is None:
            return None
        result, _stored_at = cached
        return dict(result)


def _store_motion_dedup(dedup_key: str | None, result: dict[str, object]) -> None:
    if dedup_key is None or result.get("success") is not True:
        return
    now = time.monotonic()
    with _motion_dedup_lock:
        _prune_motion_dedup_cache(now)
        _motion_dedup_cache[dedup_key] = (dict(result), now)


def _build_robot_snapshot(lifespan: AppContext) -> dict[str, object]:
    publisher = lifespan.publisher.health()
    face_recognition = lifespan.face_recognition.get_recognized_faces()
    tour_navigation = lifespan.tour_navigation.current_status()
    health_payload = {
        "robot_control_ready": bool(publisher.get("ros_ready")),
        "camera_ready": bool(lifespan.camera.health().get("camera_ready")),
        "face_recognition_ready": bool(lifespan.face_recognition.health().get("face_recognition_ready")),
        "face_registration_ready": bool(lifespan.face_registration.health().get("face_registration_ready")),
        "navigation_ready": bool(lifespan.tour_navigation.health().get("nav2_ready")),
        "motion_ready": bool(lifespan.motion.health().get("ros_ready")),
        "sensors_ready": bool(lifespan.sensors.health().get("ros_ready")),
        "motion_confirmable": bool(
            lifespan.motion.health().get("ros_ready")
            and lifespan.sensors.health().get("odom_received")
            and lifespan.sensors.health().get("odom_fresh")
        ),
    }
    battery_payload = lifespan.sensors.get_battery() if lifespan.sensors.health().get("battery_received") else {}
    scan_payload = lifespan.sensors.get_laser_scan() if lifespan.sensors.health().get("scan_received") else {}
    services = [
        {
            "id": "ros2",
            "machine_id": "robot-pc",
            "name": "ROS 2",
            "status": "healthy" if publisher.get("ros_ready") else "warning",
            "last_heartbeat": _utc_now(),
            "detail": publisher.get("startup_error") or "ROS publisher lifecycle available.",
        },
        {
            "id": "navigation",
            "machine_id": "robot-pc",
            "name": "Navigation",
            "status": "healthy" if health_payload["navigation_ready"] else "warning",
            "last_heartbeat": _utc_now(),
            "detail": lifespan.tour_navigation.health().get("readiness_detail") or "Navigation status available.",
        },
        {
            "id": "sensors",
            "machine_id": "robot-pc",
            "name": "Sensors",
            "status": "healthy" if health_payload["sensors_ready"] else "warning",
            "last_heartbeat": _utc_now(),
            "detail": "Robot sensors heartbeat updated.",
        },
        {
            "id": "robot-control",
            "machine_id": "robot-pc",
            "name": "Robot control",
            "status": "healthy" if health_payload["robot_control_ready"] else "warning",
            "last_heartbeat": _utc_now(),
            "detail": "Robot control providers are running.",
        },
    ]
    machine_health = "healthy"
    if any(item["status"] != "healthy" for item in services):
        machine_health = "warning"
    return {
        "machine_health": machine_health,
        "summary": "Robot readiness and telemetry snapshot updated.",
        "services": services,
        "turn_id": tour_navigation.get("turn_id"),
        "robot_readiness": {
            "navigation_ready": health_payload["navigation_ready"],
            "motion_confirmable": health_payload["motion_confirmable"],
            "odom_fresh": lifespan.sensors.health().get("odom_fresh"),
            "battery_percent": battery_payload.get("percentage"),
            "nearest_obstacle_m": scan_payload.get("nearest_obstacle_m"),
        },
        "robot_action_state": {
            "kind": "navigation" if tour_navigation.get("active_goal") else "idle",
            "target_stop": tour_navigation.get("active_stop_id"),
            "action_status": tour_navigation.get("status"),
            "distance_remaining_m": tour_navigation.get("distance_remaining_m"),
            "recovery_count": tour_navigation.get("recovery_count", 0),
            "replan_count": tour_navigation.get("replan_count", 0),
            "last_event_note": tour_navigation.get("last_event_note"),
            "action_id": tour_navigation.get("action_id"),
        },
        "personalization": {
            "recognized_faces": face_recognition.get("faces", []),
            "register_face_offered": False,
            "memory_activity": [],
        },
    }


def _emit_tool_started(
    lifespan: AppContext,
    *,
    tool_name: str,
    execution_id: str,
    turn_id: str | None = None,
    session_id: str | None = None,
    parent_session_id: str | None = None,
    summary: str,
    args_summary: str | None = None,
) -> None:
    if lifespan.observability is None:
        return
    lifespan.observability.emit_event(
        {
            "id": f"{execution_id}-start",
            "turn_id": turn_id,
            "machine_id": "robot-pc",
            "service_id": "robot-control",
            "type": "tool_call",
            "status": "healthy",
            "timestamp": _utc_now(),
            "payload_summary": summary,
            "raw": {
                "tool_execution_id": execution_id,
                "tool_name": tool_name,
                "tool_kind": "mcp",
                "session_id": session_id,
                "parent_session_id": parent_session_id,
                "child_session_id": session_id,
                "turn_id": turn_id,
                "args_summary": args_summary,
            },
        }
    )


def _emit_tool_finished(
    lifespan: AppContext,
    *,
    tool_name: str,
    execution_id: str,
    result: object,
    turn_id: str | None = None,
    session_id: str | None = None,
    parent_session_id: str | None = None,
    started_at: float | None = None,
) -> None:
    if lifespan.observability is None:
        return
    status = "healthy"
    error = None
    if isinstance(result, dict) and result.get("success") is False:
        status = "error"
        error = result.get("error")
    latency_ms = None
    if started_at is not None:
        latency_ms = int((time.perf_counter() - started_at) * 1000)
    result_summary = _summarize_result(tool_name, result)
    lifespan.observability.emit_event(
        {
            "id": f"{execution_id}-finish",
            "turn_id": turn_id,
            "machine_id": "robot-pc",
            "service_id": "robot-control",
            "type": "tool_error" if status == "error" else "tool_result",
            "status": status,
            "timestamp": _utc_now(),
            "latency_ms": latency_ms,
            "payload_summary": result_summary,
            "raw": {
                "tool_execution_id": execution_id,
                "tool_name": tool_name,
                "tool_kind": "mcp",
                "session_id": session_id,
                "parent_session_id": parent_session_id,
                "child_session_id": session_id,
                "turn_id": turn_id,
                "result_summary": result_summary,
                "error": error,
                "result": result,
            },
        }
    )


def _build_app_context() -> AppContext:
    publisher = EyeExpressionPublisher()
    camera = CameraCaptureProvider(
        image_topic=os.getenv("MORETEA_CAMERA_TOPIC", CAMERA_TOPIC),
        topic_kind=os.getenv("MORETEA_CAMERA_TOPIC_KIND", CAMERA_TOPIC_KIND),
    )
    face_recognition = FaceRecognitionStatusProvider(
        topic=os.getenv("MORETEA_FACE_RECOGNITION_TOPIC", FACE_RECOGNITION_TOPIC)
    )
    face_registration = FaceRegistrationProvider(
        service_name=os.getenv("MORETEA_FACE_REGISTRATION_SERVICE", FACE_REGISTRATION_SERVICE),
        db_path=os.getenv("MORETEA_FACE_DB_PATH", FACE_DB_PATH),
    )
    navigation = NavigationStatusProvider()
    tour_navigation = TourNavigationExecutor()
    motion = RobotMotionProvider(topic=os.getenv("MORETEA_CMD_VEL_TOPIC", CMD_VEL_TOPIC))
    sensors = RobotSensorProvider(
        odom_topic=os.getenv("MORETEA_ODOM_TOPIC", ODOM_TOPIC),
        battery_topic=os.getenv("MORETEA_BATTERY_TOPIC", BATTERY_TOPIC),
        scan_topic=os.getenv("MORETEA_SCAN_TOPIC", SCAN_TOPIC),
    )
    observability = RobotObservabilityReporter()
    publisher_start_error: str | None = None
    camera_start_error: str | None = None
    face_recognition_start_error: str | None = None
    face_registration_start_error: str | None = None
    navigation_start_error: str | None = None
    tour_navigation_start_error: str | None = None
    motion_start_error: str | None = None
    sensors_start_error: str | None = None
    tour_stops_error: str | None = None
    tour_stops: tuple[TourStop, ...] = ()

    try:
        publisher.start()
    except Exception as exc:  # noqa: BLE001
        publisher_start_error = str(exc)

    try:
        camera.start()
    except Exception as exc:  # noqa: BLE001
        camera_start_error = str(exc)

    try:
        face_recognition.start()
    except Exception as exc:  # noqa: BLE001
        face_recognition_start_error = str(exc)

    try:
        face_registration.start()
    except Exception as exc:  # noqa: BLE001
        face_registration_start_error = str(exc)

    try:
        navigation.start()
    except Exception as exc:  # noqa: BLE001
        navigation_start_error = str(exc)

    try:
        tour_navigation.start()
    except Exception as exc:  # noqa: BLE001
        tour_navigation_start_error = str(exc)

    try:
        motion.start()
    except Exception as exc:  # noqa: BLE001
        motion_start_error = str(exc)

    try:
        sensors.start()
    except Exception as exc:  # noqa: BLE001
        sensors_start_error = str(exc)

    try:
        tour_stops = load_tour_stops()
    except Exception as exc:  # noqa: BLE001
        tour_stops_error = str(exc)

    return AppContext(
        publisher=publisher,
        camera=camera,
        face_recognition=face_recognition,
        face_registration=face_registration,
        navigation=navigation,
        tour_navigation=tour_navigation,
        motion=motion,
        sensors=sensors,
        tour_stops=tour_stops,
        observability=observability,
        publisher_start_error=publisher_start_error,
        camera_start_error=camera_start_error,
        face_recognition_start_error=face_recognition_start_error,
        face_registration_start_error=face_registration_start_error,
        navigation_start_error=navigation_start_error,
        tour_navigation_start_error=tour_navigation_start_error,
        motion_start_error=motion_start_error,
        sensors_start_error=sensors_start_error,
        tour_stops_error=tour_stops_error,
    )


@asynccontextmanager
async def app_lifespan(_: FastMCP) -> AsyncIterator[AppContext]:
    """Yield the process-level AppContext, initializing it on the first request.

    FastMCP with stateless_http=True calls this lifespan for every HTTP
    request.  Using a singleton ensures ROS nodes are started exactly once
    per process instead of once per request, preventing duplicate-node
    warnings and file-descriptor exhaustion.
    """
    global _ctx_singleton
    with _ctx_singleton_lock:
        if _ctx_singleton is None:
            _ctx_singleton = _build_app_context()
            if _ctx_singleton.observability is not None:
                _ctx_singleton.observability.start(lambda: _build_robot_snapshot(_ctx_singleton))
    yield _ctx_singleton


mcp = FastMCP(
    "MoreTea Robot Control",
    instructions=(
        "Robot-side control server for MoreTea. "
        "Use health to verify ROS readiness. "
        "Use express_emotion to change the robot eyes. "
        "Use move_distance for fixed-distance travel, rotate_angle for in-place rotation, stop_motion to halt immediately. "
        "Use get_odometry for current position, get_battery for battery state, get_laser_scan for nearest obstacle distance. "
        "Use capture_image to fetch the latest buffered camera frame. "
        "Use get_recognized_faces to inspect the latest face-recognition snapshot, register_face to save a newly met person. "
        "Use list_tour_stops to inspect known tour locations, get_navigation_status to inspect Nav2 state, cancel_navigation to halt navigation. "
        "NAVIGATION: Call navigate_to_stop(stop_id) directly from the main session. "
        "It blocks until a terminal outcome is reached — do not manage polling, retries, or action IDs in prompt logic. "
        "Report the final status and detail fields from the result. "
        "Call cancel_navigation to abort. Call stop_motion for an emergency stop. "
        "MOTION: Call health before any motion request and refuse if motion_confirmable is false. "
        "Call move_distance(distance_m=...) for translation or rotate_angle(angle_deg=...) for rotation directly. "
        "Each blocks until complete. Report actual distance/angle from the result payload, not the requested value."
    ),
    stateless_http=True,
    json_response=True,
    lifespan=app_lifespan,
)


def _error_payload(message: str, **fields: object) -> dict[str, object]:
    payload: dict[str, object] = {"success": False, "error": message}
    payload.update(fields)
    return payload


def _normalize_navigation_result(payload: dict[str, object]) -> dict[str, object]:
    status = payload.get("status")
    if not isinstance(status, str) or not status:
        outcome = str(payload.get("outcome") or "")
        if outcome == "succeeded":
            status = "completed"
        elif outcome == "canceled":
            status = "cancelled"
        else:
            status = "failed"
    normalized = dict(payload)
    normalized["status"] = status
    normalized.setdefault("timed_out", status == "timed_out")
    return normalized


def _normalize_motion_result(payload: dict[str, object], *, action: str) -> dict[str, object]:
    normalized = dict(payload)
    status = "completed" if payload.get("success") else "failed"
    normalized.setdefault("status", status)
    detail = payload.get("detail")
    if not isinstance(detail, str) or not detail:
        if payload.get("success"):
            detail = f"{action.capitalize()} completed."
        else:
            detail = str(payload.get("error") or f"{action.capitalize()} failed.")
        normalized["detail"] = detail
    normalized.setdefault("timed_out", False)
    return normalized


@mcp.tool()
def health(ctx: Context[ServerSession, AppContext]) -> dict[str, object]:
    """Report whether the robot-side MCP providers are ready."""
    lifespan = ctx.request_context.lifespan_context
    execution_id = lifespan.observability.next_tool_execution_id("health") if lifespan.observability else "health"
    started_at = time.perf_counter()
    _emit_tool_started(
        lifespan,
        tool_name="health",
        execution_id=execution_id,
        summary="Robot health probe started.",
        args_summary=_summarize_args(),
    )
    publisher = lifespan.publisher.health()
    camera = lifespan.camera.health()
    face_recognition = lifespan.face_recognition.health()
    face_registration = lifespan.face_registration.health()
    navigation = lifespan.navigation.health()
    tour_navigation = lifespan.tour_navigation.health()
    motion = lifespan.motion.health()
    sensors = lifespan.sensors.health()
    motion_node_ready = bool(motion.get("ros_ready"))
    odom_received = bool(sensors.get("odom_received"))
    odom_fresh = bool(sensors.get("odom_fresh"))
    cmd_vel_publishable = motion_node_ready
    motion_confirmable = motion_node_ready and odom_received and odom_fresh
    result = {
        "success": True,
        "robot_control_ready": bool(publisher.get("ros_ready")),
        "camera_ready": bool(camera.get("camera_ready")),
        "face_recognition_ready": bool(face_recognition.get("face_recognition_ready")),
        "face_registration_ready": bool(face_registration.get("face_registration_ready")),
        "navigation_ready": bool(tour_navigation.get("nav2_ready")),
        "motion_ready": motion_node_ready,
        "sensors_ready": bool(sensors.get("ros_ready")),
        "motion_node_ready": motion_node_ready,
        "odom_received": odom_received,
        "cmd_vel_publishable": cmd_vel_publishable,
        "motion_confirmable": motion_confirmable,
        "publisher": publisher,
        "camera": camera,
        "face_recognition": face_recognition,
        "face_registration": face_registration,
        "navigation": navigation,
        "tour_navigation": tour_navigation,
        "motion": motion,
        "sensors": sensors,
        "tour_stop_count": len(lifespan.tour_stops),
        "startup_errors": {
            "publisher": lifespan.publisher_start_error,
            "camera": lifespan.camera_start_error,
            "face_recognition": lifespan.face_recognition_start_error,
            "face_registration": lifespan.face_registration_start_error,
            "navigation": lifespan.navigation_start_error,
            "tour_navigation": lifespan.tour_navigation_start_error,
            "motion": lifespan.motion_start_error,
            "sensors": lifespan.sensors_start_error,
            "tour_stops": lifespan.tour_stops_error,
        },
    }
    _emit_tool_finished(lifespan, tool_name="health", execution_id=execution_id, result=result, started_at=started_at)
    return result


@mcp.tool()
def express_emotion(mood: str, ctx: Context[ServerSession, AppContext]) -> dict[str, object]:
    """Publish one named eye expression to the robot."""
    publisher = ctx.request_context.lifespan_context.publisher
    lifespan = ctx.request_context.lifespan_context
    execution_id = lifespan.observability.next_tool_execution_id("express_emotion") if lifespan.observability else "express_emotion"
    started_at = time.perf_counter()
    _emit_tool_started(
        lifespan,
        tool_name="express_emotion",
        execution_id=execution_id,
        summary="Eye expression tool started.",
        args_summary=_summarize_args(mood=mood),
    )
    try:
        result = publisher.publish_emotion(mood)
    except (RuntimeError, ValueError) as exc:
        result = _error_payload(str(exc), mood=mood)
    _emit_tool_finished(lifespan, tool_name="express_emotion", execution_id=execution_id, result=result, started_at=started_at)
    return result


@mcp.tool()
def capture_image(ctx: Context[ServerSession, AppContext]):
    """Return the latest buffered camera frame as an image the model can see."""
    lifespan = ctx.request_context.lifespan_context
    execution_id = lifespan.observability.next_tool_execution_id("capture_image") if lifespan.observability else "capture_image"
    started_at = time.perf_counter()
    _emit_tool_started(
        lifespan,
        tool_name="capture_image",
        execution_id=execution_id,
        summary="Camera capture tool started.",
        args_summary=_summarize_args(),
    )
    try:
        result = lifespan.camera.capture_image()
    except RuntimeError as exc:
        result = _error_payload(str(exc))
        _emit_tool_finished(lifespan, tool_name="capture_image", execution_id=execution_id, result=result, started_at=started_at)
        return result

    _emit_tool_finished(lifespan, tool_name="capture_image", execution_id=execution_id, result=result, started_at=started_at)
    return [ImageContent(type="image", data=result["image_base64"], mimeType="image/jpeg")]


@mcp.tool()
def get_recognized_faces(ctx: Context[ServerSession, AppContext]) -> dict[str, object]:
    """Return the latest structured face-recognition snapshot from the robot."""
    lifespan = ctx.request_context.lifespan_context
    execution_id = lifespan.observability.next_tool_execution_id("get_recognized_faces") if lifespan.observability else "get_recognized_faces"
    started_at = time.perf_counter()
    _emit_tool_started(
        lifespan,
        tool_name="get_recognized_faces",
        execution_id=execution_id,
        summary="Face recognition snapshot requested.",
        args_summary=_summarize_args(),
    )
    result = lifespan.face_recognition.get_recognized_faces()
    if lifespan.observability is not None:
        lifespan.observability.emit_event(
            {
                "id": f"face-check-{uuid4()}",
                "turn_id": None,
                "machine_id": "robot-pc",
                "service_id": "robot-control",
                "type": "face_check",
                "status": "healthy",
                "timestamp": _utc_now(),
                "payload_summary": "Face recognition snapshot updated.",
                "raw": {"recognized_faces": result.get("faces", [])},
            }
        )
    _emit_tool_finished(lifespan, tool_name="get_recognized_faces", execution_id=execution_id, result=result, started_at=started_at)
    return result


@mcp.tool()
def register_face(name: str, ctx: Context[ServerSession, AppContext]) -> dict[str, object]:
    """Register one newly met person's face through the robot-side ROS service."""
    lifespan = ctx.request_context.lifespan_context
    provider = lifespan.face_registration
    execution_id = lifespan.observability.next_tool_execution_id("register_face") if lifespan.observability else "register_face"
    started_at = time.perf_counter()
    _emit_tool_started(
        lifespan,
        tool_name="register_face",
        execution_id=execution_id,
        summary="Face registration requested.",
        args_summary=_summarize_args(name=name.strip()),
    )
    try:
        result = provider.register_face(name)
    except ValueError as exc:
        normalized_name = name.strip()
        result = _error_payload(str(exc), name=normalized_name, duplicate="already registered" in str(exc).lower(), db_path=str(provider._db_path))
    except RuntimeError as exc:
        result = _error_payload(str(exc), name=name.strip(), duplicate=False, db_path=str(provider._db_path))
    _emit_tool_finished(lifespan, tool_name="register_face", execution_id=execution_id, result=result, started_at=started_at)
    return result


@mcp.tool()
def get_navigation_status(ctx: Context[ServerSession, AppContext]) -> dict[str, object]:
    """Report current read-only navigation status from the robot."""
    lifespan = ctx.request_context.lifespan_context
    execution_id = lifespan.observability.next_tool_execution_id("get_navigation_status") if lifespan.observability else "get_navigation_status"
    started_at = time.perf_counter()
    _emit_tool_started(
        lifespan,
        tool_name="get_navigation_status",
        execution_id=execution_id,
        summary="Navigation status requested.",
        args_summary=_summarize_args(),
    )
    provider = lifespan.navigation
    try:
        status = provider.status()
    except RuntimeError as exc:
        result = _error_payload(str(exc))
        _emit_tool_finished(lifespan, tool_name="get_navigation_status", execution_id=execution_id, result=result, started_at=started_at)
        return result
    live_status = lifespan.tour_navigation.current_status()
    if live_status.get("active_goal"):
        status["available"] = True
        status["is_navigating"] = True
        status["distance_remaining_m"] = live_status.get("distance_remaining_m")
        status["recovery_count"] = live_status.get("recovery_count", 0)
        status["replan_count"] = live_status.get("replan_count", 0)
        status["last_event_note"] = live_status.get("last_event_note")
        distance = live_status.get("distance_remaining_m")
        if distance is None:
            status["status_text"] = "The robot is navigating, but distance feedback is not available yet."
        else:
            status["status_text"] = f"Approximately {float(distance):.1f} metres remain."
    if live_status.get("active_stop_id"):
        status["active_stop_id"] = live_status["active_stop_id"]
    if live_status.get("active_stop_name"):
        status["active_stop_name"] = live_status["active_stop_name"]
    if live_status.get("action_id") is not None:
        status["action_id"] = live_status["action_id"]
    if live_status.get("status") is not None:
        status["action_status"] = live_status["status"]
    if live_status.get("detail") is not None:
        status["action_detail"] = live_status["detail"]
    if live_status.get("last_outcome") is not None:
        status["last_outcome"] = live_status["last_outcome"]
    _emit_tool_finished(lifespan, tool_name="get_navigation_status", execution_id=execution_id, result=status, started_at=started_at)
    return status


@mcp.tool()
def list_tour_stops(ctx: Context[ServerSession, AppContext]) -> dict[str, object]:
    """List configured tour stops and aliases by stable stop id."""
    lifespan = ctx.request_context.lifespan_context
    lifespan = ctx.request_context.lifespan_context
    execution_id = lifespan.observability.next_tool_execution_id("list_tour_stops") if lifespan.observability else "list_tour_stops"
    started_at = time.perf_counter()
    _emit_tool_started(
        lifespan,
        tool_name="list_tour_stops",
        execution_id=execution_id,
        summary="Tour stop catalog requested.",
        args_summary=_summarize_args(),
    )
    result = {
        "success": True,
        "count": len(lifespan.tour_stops),
        "stops": [serialize_stop(stop) for stop in lifespan.tour_stops],
    }
    _emit_tool_finished(lifespan, tool_name="list_tour_stops", execution_id=execution_id, result=result, started_at=started_at)
    return result


@mcp.tool()
def navigate_to_stop(
    stop_id: str,
    ctx: Context[ServerSession, AppContext],
) -> dict[str, object]:
    """Navigate to a named tour stop and block until a terminal outcome is available."""
    lifespan = ctx.request_context.lifespan_context
    tour_navigation = lifespan.tour_navigation
    correlation = _request_correlation(ctx)
    execution_id = lifespan.observability.next_tool_execution_id("navigate_to_stop") if lifespan.observability else "navigate_to_stop"
    started_at = time.perf_counter()
    _emit_tool_started(
        lifespan,
        tool_name="navigate_to_stop",
        execution_id=execution_id,
        turn_id=correlation["turn_id"],
        session_id=correlation["session_id"],
        parent_session_id=correlation["parent_session_id"],
        summary=f"Navigation requested for stop `{stop_id}`.",
        args_summary=_summarize_args(stop_id=stop_id),
    )

    target = next((s for s in lifespan.tour_stops if s.id == stop_id.strip()), None)
    if target is None:
        result = _error_payload(
            f"Unknown stop_id '{stop_id}'.",
            stop_id=stop_id,
            available_stop_ids=[s.id for s in lifespan.tour_stops],
            status="failed",
            timed_out=False,
        )
        _emit_tool_finished(
            lifespan,
            tool_name="navigate_to_stop",
            execution_id=execution_id,
            result=result,
            turn_id=correlation["turn_id"],
            session_id=correlation["session_id"],
            parent_session_id=correlation["parent_session_id"],
            started_at=started_at,
        )
        return result

    result = _normalize_navigation_result(tour_navigation.navigate_to_stop(target))
    _emit_tool_finished(
        lifespan,
        tool_name="navigate_to_stop",
        execution_id=execution_id,
        result=result,
        turn_id=correlation["turn_id"],
        session_id=correlation["session_id"],
        parent_session_id=correlation["parent_session_id"],
        started_at=started_at,
    )
    return result


@mcp.tool()
def cancel_navigation(
    ctx: Context[ServerSession, AppContext],
    action_id: str | None = None,
) -> dict[str, object]:
    """Cancel any active Humble Nav2 navigation started through this server."""
    lifespan = ctx.request_context.lifespan_context
    correlation = _request_correlation(ctx)
    execution_id = lifespan.observability.next_tool_execution_id("cancel_navigation") if lifespan.observability else "cancel_navigation"
    started_at = time.perf_counter()
    _emit_tool_started(
        lifespan,
        tool_name="cancel_navigation",
        execution_id=execution_id,
        turn_id=correlation["turn_id"],
        session_id=correlation["session_id"],
        parent_session_id=correlation["parent_session_id"],
        summary="Navigation cancellation requested.",
        args_summary=_summarize_args(action_id=action_id),
    )
    result = lifespan.tour_navigation.cancel_navigation(action_id=action_id)
    _emit_tool_finished(
        lifespan,
        tool_name="cancel_navigation",
        execution_id=execution_id,
        result=result,
        turn_id=correlation["turn_id"],
        session_id=correlation["session_id"],
        parent_session_id=correlation["parent_session_id"],
        started_at=started_at,
    )
    return result


@mcp.tool()
def move_distance(
    ctx: Context[ServerSession, AppContext],
    distance_m: float,
    speed_m_s: float = 0.15,
    allow_open_loop: bool = False,
) -> dict[str, object]:
    """Move the robot forward or backward a fixed distance.

    distance_m: metres to travel. Positive = forward, negative = backward.
    speed_m_s: travel speed in m/s. Defaults to 0.15 m/s. Clamped to 0.4 m/s.
    Uses closed-loop odometry feedback when available (accurate to ~2 cm).
    Refuses unconfirmed open-loop motion unless allow_open_loop=True.
    Returns: success, mode (closed_loop|open_loop_override), requested_distance_m,
             actual_distance_m (closed_loop only), timed_out.
    """
    lifespan = ctx.request_context.lifespan_context
    correlation = _request_correlation(ctx)
    execution_id = lifespan.observability.next_tool_execution_id("move_distance") if lifespan.observability else "move_distance"
    started_at = time.perf_counter()
    dedup_key = _motion_dedup_key(
        correlation["turn_id"],
        "move_distance",
        distance_m=distance_m,
        speed_m_s=speed_m_s,
        allow_open_loop=allow_open_loop,
    )
    _emit_tool_started(
        lifespan,
        tool_name="move_distance",
        execution_id=execution_id,
        turn_id=correlation["turn_id"],
        session_id=correlation["session_id"],
        parent_session_id=correlation["parent_session_id"],
        summary="Distance move requested.",
        args_summary=_summarize_args(distance_m=distance_m, speed_m_s=speed_m_s, allow_open_loop=allow_open_loop),
    )
    cached = _check_motion_dedup(dedup_key)
    if cached is not None:
        result = {**cached, "deduplicated": True}
        _emit_tool_finished(
            lifespan,
            tool_name="move_distance",
            execution_id=execution_id,
            result=result,
            turn_id=correlation["turn_id"],
            session_id=correlation["session_id"],
            parent_session_id=correlation["parent_session_id"],
            started_at=started_at,
        )
        return result
    try:
        app = lifespan
        pos_fn = None
        if app.sensors is not None:
            pos_fn = app.sensors.get_position
        result = _normalize_motion_result(
            app.motion.move_distance(
                distance_m=distance_m,
                speed_m_s=speed_m_s,
                pos_fn=pos_fn,
                allow_open_loop=allow_open_loop,
                feedback_available_fn=app.sensors.has_fresh_odometry if app.sensors is not None else None,
            ),
            action="translation",
        )
    except RuntimeError as exc:
        result = _normalize_motion_result(_error_payload(str(exc)), action="translation")
    _store_motion_dedup(dedup_key, result)
    _emit_tool_finished(
        lifespan,
        tool_name="move_distance",
        execution_id=execution_id,
        result=result,
        turn_id=correlation["turn_id"],
        session_id=correlation["session_id"],
        parent_session_id=correlation["parent_session_id"],
        started_at=started_at,
    )
    return result


@mcp.tool()
def rotate_angle(
    ctx: Context[ServerSession, AppContext],
    angle_deg: float,
    speed_rad_s: float = 0.4,
    allow_open_loop: bool = False,
) -> dict[str, object]:
    """Rotate the robot in place by an exact number of degrees.

    Use this tool whenever the user asks to turn, rotate, spin, or face a
    different direction by a specific angle. Do NOT use move() with angular_z
    for angle-based rotation — this tool uses odometry feedback for accuracy.

    angle_deg: degrees to rotate. Positive = counterclockwise (left turn),
               negative = clockwise (right turn).
               Examples: 90 = quarter-turn left, -90 = quarter-turn right,
               180 = half-turn (face backwards), 360 = full spin.
    speed_rad_s: rotation speed in rad/s. Defaults to 0.4 rad/s. Clamped to 0.8 rad/s.
                 For 360° full spins, prefer 0.8 rad/s for speed.

    Uses closed-loop odometry feedback when available (accurate to ~3°).
    Refuses unconfirmed open-loop rotation unless allow_open_loop=True.
    Returns: success, mode (closed_loop|open_loop_override), requested_angle_deg,
             actual_angle_deg (closed_loop only), timed_out.
    """
    lifespan = ctx.request_context.lifespan_context
    correlation = _request_correlation(ctx)
    execution_id = lifespan.observability.next_tool_execution_id("rotate_angle") if lifespan.observability else "rotate_angle"
    started_at = time.perf_counter()
    dedup_key = _motion_dedup_key(
        correlation["turn_id"],
        "rotate_angle",
        angle_deg=angle_deg,
        speed_rad_s=speed_rad_s,
        allow_open_loop=allow_open_loop,
    )
    _emit_tool_started(
        lifespan,
        tool_name="rotate_angle",
        execution_id=execution_id,
        turn_id=correlation["turn_id"],
        session_id=correlation["session_id"],
        parent_session_id=correlation["parent_session_id"],
        summary="Rotation move requested.",
        args_summary=_summarize_args(angle_deg=angle_deg, speed_rad_s=speed_rad_s, allow_open_loop=allow_open_loop),
    )
    cached = _check_motion_dedup(dedup_key)
    if cached is not None:
        result = {**cached, "deduplicated": True}
        _emit_tool_finished(
            lifespan,
            tool_name="rotate_angle",
            execution_id=execution_id,
            result=result,
            turn_id=correlation["turn_id"],
            session_id=correlation["session_id"],
            parent_session_id=correlation["parent_session_id"],
            started_at=started_at,
        )
        return result
    try:
        app = lifespan
        yaw_fn = None
        if app.sensors is not None:
            yaw_fn = app.sensors.get_yaw
        result = _normalize_motion_result(
            app.motion.rotate_angle(
                angle_deg=angle_deg,
                speed_rad_s=speed_rad_s,
                yaw_fn=yaw_fn,
                allow_open_loop=allow_open_loop,
                feedback_available_fn=app.sensors.has_fresh_odometry if app.sensors is not None else None,
            ),
            action="rotation",
        )
    except RuntimeError as exc:
        result = _normalize_motion_result(_error_payload(str(exc)), action="rotation")
    _store_motion_dedup(dedup_key, result)
    _emit_tool_finished(
        lifespan,
        tool_name="rotate_angle",
        execution_id=execution_id,
        result=result,
        turn_id=correlation["turn_id"],
        session_id=correlation["session_id"],
        parent_session_id=correlation["parent_session_id"],
        started_at=started_at,
    )
    return result


@mcp.tool()
def stop_motion(ctx: Context[ServerSession, AppContext]) -> dict[str, object]:
    """Publish a zero-velocity Twist immediately to halt all movement."""
    lifespan = ctx.request_context.lifespan_context
    correlation = _request_correlation(ctx)
    execution_id = lifespan.observability.next_tool_execution_id("stop_motion") if lifespan.observability else "stop_motion"
    started_at = time.perf_counter()
    dedup_key = _motion_dedup_key(correlation["turn_id"], "stop_motion")
    _emit_tool_started(
        lifespan,
        tool_name="stop_motion",
        execution_id=execution_id,
        turn_id=correlation["turn_id"],
        session_id=correlation["session_id"],
        parent_session_id=correlation["parent_session_id"],
        summary="Emergency stop requested.",
        args_summary=_summarize_args(),
    )
    cached = _check_motion_dedup(dedup_key)
    if cached is not None:
        result = {**cached, "deduplicated": True}
        _emit_tool_finished(
            lifespan,
            tool_name="stop_motion",
            execution_id=execution_id,
            result=result,
            turn_id=correlation["turn_id"],
            session_id=correlation["session_id"],
            parent_session_id=correlation["parent_session_id"],
            started_at=started_at,
        )
        return result
    try:
        result = lifespan.motion.stop()
    except RuntimeError as exc:
        result = _error_payload(str(exc))
    _store_motion_dedup(dedup_key, result)
    _emit_tool_finished(
        lifespan,
        tool_name="stop_motion",
        execution_id=execution_id,
        result=result,
        turn_id=correlation["turn_id"],
        session_id=correlation["session_id"],
        parent_session_id=correlation["parent_session_id"],
        started_at=started_at,
    )
    return result


@mcp.tool()
def get_odometry(ctx: Context[ServerSession, AppContext]) -> dict[str, object]:
    """Return the latest odometry reading: position (x, y) and velocity."""
    lifespan = ctx.request_context.lifespan_context
    execution_id = lifespan.observability.next_tool_execution_id("get_odometry") if lifespan.observability else "get_odometry"
    started_at = time.perf_counter()
    _emit_tool_started(
        lifespan,
        tool_name="get_odometry",
        execution_id=execution_id,
        summary="Odometry requested.",
        args_summary=_summarize_args(),
    )
    try:
        result = lifespan.sensors.get_odometry()
    except RuntimeError as exc:
        result = _error_payload(str(exc))
    _emit_tool_finished(lifespan, tool_name="get_odometry", execution_id=execution_id, result=result, started_at=started_at)
    return result


@mcp.tool()
def get_battery(ctx: Context[ServerSession, AppContext]) -> dict[str, object]:
    """Return the latest battery state: percentage and voltage."""
    lifespan = ctx.request_context.lifespan_context
    execution_id = lifespan.observability.next_tool_execution_id("get_battery") if lifespan.observability else "get_battery"
    started_at = time.perf_counter()
    _emit_tool_started(
        lifespan,
        tool_name="get_battery",
        execution_id=execution_id,
        summary="Battery snapshot requested.",
        args_summary=_summarize_args(),
    )
    try:
        result = lifespan.sensors.get_battery()
    except RuntimeError as exc:
        result = _error_payload(str(exc))
    _emit_tool_finished(lifespan, tool_name="get_battery", execution_id=execution_id, result=result, started_at=started_at)
    return result


@mcp.tool()
def get_laser_scan(ctx: Context[ServerSession, AppContext]) -> dict[str, object]:
    """Return a summary of the latest laser scan: nearest and farthest obstacle distances."""
    lifespan = ctx.request_context.lifespan_context
    execution_id = lifespan.observability.next_tool_execution_id("get_laser_scan") if lifespan.observability else "get_laser_scan"
    started_at = time.perf_counter()
    _emit_tool_started(
        lifespan,
        tool_name="get_laser_scan",
        execution_id=execution_id,
        summary="Laser scan snapshot requested.",
        args_summary=_summarize_args(),
    )
    try:
        result = lifespan.sensors.get_laser_scan()
    except RuntimeError as exc:
        result = _error_payload(str(exc))
    _emit_tool_finished(lifespan, tool_name="get_laser_scan", execution_id=execution_id, result=result, started_at=started_at)
    return result


def _env(name: str, legacy_name: str, default: str) -> str:
    return os.getenv(name) or os.getenv(legacy_name) or default


def _is_loopback_host(host: str) -> bool:
    normalized = host.strip().lower()
    if normalized in {"localhost", "127.0.0.1", "::1"}:
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False


def build_streamable_http_app() -> ASGIApp:
    """Wrap the FastMCP ASGI app with cheap probe responses for bridge startup."""
    mcp_app = mcp.streamable_http_app()
    streamable_http_path = mcp.settings.streamable_http_path
    probe_headers = {"Allow": "GET, POST, DELETE, OPTIONS, HEAD"}

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope.get("path") == streamable_http_path:
            method = str(scope.get("method", "")).upper()
            if method == "OPTIONS":
                await Response(status_code=204, headers=probe_headers)(scope, receive, send)
                return
            if method == "HEAD":
                await Response(status_code=200, headers=probe_headers)(scope, receive, send)
                return

        await mcp_app(scope, receive, send)

    return app


def main() -> None:
    host = _env("MORETEA_ROBOT_MCP_HOST", "MORETEA_EYE_MCP_HOST", "127.0.0.1")
    port = int(_env("MORETEA_ROBOT_MCP_PORT", "MORETEA_EYE_MCP_PORT", "8765"))
    path = _env("MORETEA_ROBOT_MCP_PATH", "MORETEA_EYE_MCP_PATH", "/mcp")
    allow_nonlocal = os.getenv("MORETEA_ROBOT_MCP_ALLOW_NONLOCAL", "0").strip().lower() in {"1", "true", "yes"}

    if not _is_loopback_host(host) and not allow_nonlocal:
        raise RuntimeError(
            "Refusing non-loopback MCP bind without MORETEA_ROBOT_MCP_ALLOW_NONLOCAL=1. "
            "Use loopback plus SSH tunneling by default."
        )

    mcp.settings.host = host
    mcp.settings.port = port
    mcp.settings.streamable_http_path = path
    uvicorn.run(build_streamable_http_app(), host=host, port=port)


if __name__ == "__main__":
    main()
