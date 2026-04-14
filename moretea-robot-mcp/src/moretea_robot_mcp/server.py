from __future__ import annotations

import ipaddress
import os
import threading
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

import uvicorn
from starlette.responses import Response
from starlette.types import ASGIApp, Receive, Scope, Send

from .camera_capture import CAMERA_TOPIC, CAMERA_TOPIC_KIND, CameraCaptureProvider
from .face_registration import FACE_DB_PATH, FACE_REGISTRATION_SERVICE, FaceRegistrationProvider
from .face_recognition_status import FACE_RECOGNITION_TOPIC, FaceRecognitionStatusProvider
from .navigation_status import NavigationStatusProvider
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
        "NAVIGATION (mandatory — subagent pattern only): "
        "Never call navigate_to_stop from the main interactive turn. Always spawn a background subagent via sessions_spawn and delegate navigation to it. "
        "The subagent calls navigate_to_stop(stop_id) to start navigation, then calls navigate_to_stop(stop_id, action_id=...) to resume after each return. "
        "On event='replan' or 'recovery': speak last_event_note to the user via sessions_send, then call navigate_to_stop again with the same action_id. "
        "On timed_out=True: call navigate_to_stop again silently with the same action_id (no user message needed). "
        "On terminal status (completed/failed/cancelled): announce the outcome, done. "
        "MOTION (mandatory — subagent pattern only): "
        "Never call move_distance or rotate_angle from the main interactive turn — they block for up to 10 s. "
        "Always spawn a background subagent via sessions_spawn. "
        "The subagent calls move_distance(distance_m=...) for translation or rotate_angle(angle_deg=...) for rotation — "
        "each blocks until complete, then reports the outcome to the main session via sessions_send. "
        "stop_motion may be called directly from the main turn for emergency stops."
    ),
    stateless_http=True,
    json_response=True,
    lifespan=app_lifespan,
)


def _error_payload(message: str, **fields: object) -> dict[str, object]:
    payload: dict[str, object] = {"success": False, "error": message}
    payload.update(fields)
    return payload


@mcp.tool()
def health(ctx: Context[ServerSession, AppContext]) -> dict[str, object]:
    """Report whether the robot-side MCP providers are ready."""
    lifespan = ctx.request_context.lifespan_context
    publisher = lifespan.publisher.health()
    camera = lifespan.camera.health()
    face_recognition = lifespan.face_recognition.health()
    face_registration = lifespan.face_registration.health()
    navigation = lifespan.navigation.health()
    tour_navigation = lifespan.tour_navigation.health()
    return {
        "success": True,
        "robot_control_ready": bool(publisher.get("ros_ready")),
        "camera_ready": bool(camera.get("camera_ready")),
        "face_recognition_ready": bool(face_recognition.get("face_recognition_ready")),
        "face_registration_ready": bool(face_registration.get("face_registration_ready")),
        "navigation_ready": bool(tour_navigation.get("nav2_ready")),
        "motion_ready": bool(lifespan.motion.health().get("ros_ready")),
        "sensors_ready": bool(lifespan.sensors.health().get("ros_ready")),
        "publisher": publisher,
        "camera": camera,
        "face_recognition": face_recognition,
        "face_registration": face_registration,
        "navigation": navigation,
        "tour_navigation": tour_navigation,
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


@mcp.tool()
def express_emotion(mood: str, ctx: Context[ServerSession, AppContext]) -> dict[str, object]:
    """Publish one named eye expression to the robot."""
    publisher = ctx.request_context.lifespan_context.publisher
    try:
        return publisher.publish_emotion(mood)
    except (RuntimeError, ValueError) as exc:
        return _error_payload(str(exc), mood=mood)


@mcp.tool()
def capture_image(ctx: Context[ServerSession, AppContext]):
    """Return the latest buffered camera frame as an image the model can see."""
    try:
        result = ctx.request_context.lifespan_context.camera.capture_image()
    except RuntimeError as exc:
        return _error_payload(str(exc))

    return [ImageContent(type="image", data=result["image_base64"], mimeType="image/jpeg")]


@mcp.tool()
def get_recognized_faces(ctx: Context[ServerSession, AppContext]) -> dict[str, object]:
    """Return the latest structured face-recognition snapshot from the robot."""
    return ctx.request_context.lifespan_context.face_recognition.get_recognized_faces()


@mcp.tool()
def register_face(name: str, ctx: Context[ServerSession, AppContext]) -> dict[str, object]:
    """Register one newly met person's face through the robot-side ROS service."""
    provider = ctx.request_context.lifespan_context.face_registration
    try:
        return provider.register_face(name)
    except ValueError as exc:
        normalized_name = name.strip()
        return _error_payload(str(exc), name=normalized_name, duplicate="already registered" in str(exc).lower(), db_path=str(provider._db_path))
    except RuntimeError as exc:
        return _error_payload(str(exc), name=name.strip(), duplicate=False, db_path=str(provider._db_path))


@mcp.tool()
def get_navigation_status(ctx: Context[ServerSession, AppContext]) -> dict[str, object]:
    """Report current read-only navigation status from the robot."""
    lifespan = ctx.request_context.lifespan_context
    provider = lifespan.navigation
    try:
        status = provider.status()
    except RuntimeError as exc:
        return _error_payload(str(exc))
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
    return status


@mcp.tool()
def list_tour_stops(ctx: Context[ServerSession, AppContext]) -> dict[str, object]:
    """List configured tour stops and aliases by stable stop id."""
    lifespan = ctx.request_context.lifespan_context
    return {
        "success": True,
        "count": len(lifespan.tour_stops),
        "stops": [serialize_stop(stop) for stop in lifespan.tour_stops],
    }


_TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled", "timed_out"})
_NAV_STEP_CAP_S = 120.0  # 2 min — SSH loopback has no gateway timeout constraint
_NAV_POLL_S = 0.05


@mcp.tool()
def navigate_to_stop(
    stop_id: str,
    ctx: Context[ServerSession, AppContext],
    action_id: str | None = None,
    max_wait_s: float = 20.0,
) -> dict[str, object]:
    """Navigate to a named tour stop. Blocks until an event occurs or navigation terminates.

    First call: provide stop_id only — starts navigation, waits for the first event or terminal.
    Subsequent calls: provide the same stop_id AND the action_id from the previous response —
    resumes waiting for the in-progress navigation.

    Returns {action_id, status, event, timed_out, last_event_note, distance_remaining_m, ...}:
      event='replan':    robot rerouted — speak last_event_note via sessions_send, call navigate_to_stop(stop_id, action_id=...) again.
      event='recovery':  robot recovering — speak last_event_note via sessions_send, call navigate_to_stop(stop_id, action_id=...) again.
      timed_out=True:    still navigating, no event — call navigate_to_stop(stop_id, action_id=...) again silently.
      terminal status (completed/failed/cancelled): report outcome, done.

    max_wait_s: max seconds to block per call. Capped at 120s (2 min).
    """
    lifespan = ctx.request_context.lifespan_context
    tour_navigation = lifespan.tour_navigation

    if action_id is None:
        # Start new navigation
        target = next((s for s in lifespan.tour_stops if s.id == stop_id.strip()), None)
        if target is None:
            return _error_payload(
                f"Unknown stop_id '{stop_id}'.",
                stop_id=stop_id,
                available_stop_ids=[s.id for s in lifespan.tour_stops],
            )
        started = tour_navigation.start_navigation_to_stop(target)
        if not started.get("success"):
            return started
        action_id = started["action_id"]

    capped = min(float(max_wait_s), _NAV_STEP_CAP_S)
    deadline = time.monotonic() + capped

    # Establish baseline event counts before polling.
    baseline = tour_navigation.get_navigation_action_status(action_id)
    if not baseline.get("success"):
        return {**baseline, "action_id": action_id}
    baseline_replan: int = baseline.get("replan_count", 0) or 0
    baseline_recovery: int = baseline.get("recovery_count", 0) or 0

    def _result(snap: dict[str, object], *, timed_out: bool, event: str | None) -> dict[str, object]:
        return {
            "success": True,
            "action_id": action_id,
            "stop_id": snap.get("stop_id") or stop_id,
            "stop_name": snap.get("stop_name"),
            "status": snap.get("status"),
            "event": event,
            "timed_out": timed_out,
            "distance_remaining_m": snap.get("distance_remaining_m"),
            "last_event_note": snap.get("last_event_note"),
            "detail": snap.get("detail"),
        }

    while True:
        snap = tour_navigation.get_navigation_action_status(action_id)
        if not snap.get("success"):
            return {**snap, "action_id": action_id, "timed_out": False, "event": None}

        status = snap.get("status")
        # Terminal check first — completion beats any concurrent event.
        if status in _TERMINAL_STATUSES:
            return _result(snap, timed_out=False, event=None)

        # Event checks — return early so the subagent can send a reassurance via sessions_send.
        cur_replan: int = snap.get("replan_count", 0) or 0
        cur_recovery: int = snap.get("recovery_count", 0) or 0
        if cur_replan > baseline_replan:
            return _result(snap, timed_out=False, event="replan")
        if cur_recovery > baseline_recovery:
            return _result(snap, timed_out=False, event="recovery")

        if time.monotonic() >= deadline:
            return _result(snap, timed_out=True, event=None)

        time.sleep(_NAV_POLL_S)


@mcp.tool()
def cancel_navigation(
    ctx: Context[ServerSession, AppContext],
    action_id: str | None = None,
) -> dict[str, object]:
    """Cancel any active Humble Nav2 navigation started through this server."""
    return ctx.request_context.lifespan_context.tour_navigation.cancel_navigation(action_id=action_id)


@mcp.tool()
def move_distance(
    ctx: Context[ServerSession, AppContext],
    distance_m: float,
    speed_m_s: float = 0.15,
) -> dict[str, object]:
    """Move the robot forward or backward a fixed distance.

    distance_m: metres to travel. Positive = forward, negative = backward.
    speed_m_s: travel speed in m/s. Defaults to 0.15 m/s. Clamped to 0.4 m/s.
    Uses closed-loop odometry feedback when available (accurate to ~2 cm).
    Falls back to open-loop timing if odometry not yet received.
    Returns: success, mode (closed_loop|open_loop), requested_distance_m,
             actual_distance_m (closed_loop only), timed_out.
    """
    try:
        app = ctx.request_context.lifespan_context
        pos_fn = None
        if app.sensors is not None:
            pos_fn = app.sensors.get_position
        return app.motion.move_distance(
            distance_m=distance_m,
            speed_m_s=speed_m_s,
            pos_fn=pos_fn,
        )
    except RuntimeError as exc:
        return _error_payload(str(exc))


@mcp.tool()
def rotate_angle(
    ctx: Context[ServerSession, AppContext],
    angle_deg: float,
    speed_rad_s: float = 0.4,
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
                 For angles > 180°, use 0.8 rad/s to stay within the 10s timeout.

    Uses closed-loop odometry feedback when available (accurate to ~3°).
    Falls back to open-loop timing if odometry not yet received.
    Returns: success, mode (closed_loop|open_loop), requested_angle_deg,
             actual_angle_deg (closed_loop only), timed_out.
    """
    try:
        app = ctx.request_context.lifespan_context
        yaw_fn = None
        if app.sensors is not None:
            yaw_fn = app.sensors.get_yaw
        return app.motion.rotate_angle(
            angle_deg=angle_deg,
            speed_rad_s=speed_rad_s,
            yaw_fn=yaw_fn,
        )
    except RuntimeError as exc:
        return _error_payload(str(exc))


@mcp.tool()
def stop_motion(ctx: Context[ServerSession, AppContext]) -> dict[str, object]:
    """Publish a zero-velocity Twist immediately to halt all movement."""
    try:
        return ctx.request_context.lifespan_context.motion.stop()
    except RuntimeError as exc:
        return _error_payload(str(exc))


@mcp.tool()
def get_odometry(ctx: Context[ServerSession, AppContext]) -> dict[str, object]:
    """Return the latest odometry reading: position (x, y) and velocity."""
    try:
        return ctx.request_context.lifespan_context.sensors.get_odometry()
    except RuntimeError as exc:
        return _error_payload(str(exc))


@mcp.tool()
def get_battery(ctx: Context[ServerSession, AppContext]) -> dict[str, object]:
    """Return the latest battery state: percentage and voltage."""
    try:
        return ctx.request_context.lifespan_context.sensors.get_battery()
    except RuntimeError as exc:
        return _error_payload(str(exc))


@mcp.tool()
def get_laser_scan(ctx: Context[ServerSession, AppContext]) -> dict[str, object]:
    """Return a summary of the latest laser scan: nearest and farthest obstacle distances."""
    try:
        return ctx.request_context.lifespan_context.sensors.get_laser_scan()
    except RuntimeError as exc:
        return _error_payload(str(exc))


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
