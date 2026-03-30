from __future__ import annotations

import ipaddress
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from .camera_capture import CAMERA_TOPIC, CAMERA_TOPIC_KIND, CameraCaptureProvider
from .face_registration import FACE_DB_PATH, FACE_REGISTRATION_SERVICE, FaceRegistrationProvider
from .face_recognition_status import FACE_RECOGNITION_TOPIC, FaceRecognitionStatusProvider
from .navigation_status import NavigationStatusProvider
from .ros_eye_publisher import EyeExpressionPublisher
from .tour_navigation import TourNavigationExecutor
from .tour_stops import TourStop, load_tour_stops, serialize_stop

try:
    from mcp.server.fastmcp import Context, FastMCP
    from mcp.server.session import ServerSession
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


@dataclass
class AppContext:
    publisher: EyeExpressionPublisher
    camera: CameraCaptureProvider
    face_recognition: FaceRecognitionStatusProvider
    face_registration: FaceRegistrationProvider
    navigation: NavigationStatusProvider
    tour_navigation: TourNavigationExecutor
    tour_stops: tuple[TourStop, ...]
    publisher_start_error: str | None = None
    camera_start_error: str | None = None
    face_recognition_start_error: str | None = None
    face_registration_start_error: str | None = None
    navigation_start_error: str | None = None
    tour_navigation_start_error: str | None = None
    tour_stops_error: str | None = None


@asynccontextmanager
async def app_lifespan(_: FastMCP) -> AsyncIterator[AppContext]:
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
    publisher_start_error: str | None = None
    camera_start_error: str | None = None
    face_recognition_start_error: str | None = None
    face_registration_start_error: str | None = None
    navigation_start_error: str | None = None
    tour_navigation_start_error: str | None = None
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
        tour_stops = load_tour_stops()
    except Exception as exc:  # noqa: BLE001
        tour_stops_error = str(exc)

    try:
        yield AppContext(
            publisher=publisher,
            camera=camera,
            face_recognition=face_recognition,
            face_registration=face_registration,
            navigation=navigation,
            tour_navigation=tour_navigation,
            tour_stops=tour_stops,
            publisher_start_error=publisher_start_error,
            camera_start_error=camera_start_error,
            face_recognition_start_error=face_recognition_start_error,
            face_registration_start_error=face_registration_start_error,
            navigation_start_error=navigation_start_error,
            tour_navigation_start_error=tour_navigation_start_error,
            tour_stops_error=tour_stops_error,
        )
    finally:
        tour_navigation.shutdown()
        navigation.shutdown()
        face_registration.shutdown()
        face_recognition.shutdown()
        camera.shutdown()
        publisher.shutdown()


mcp = FastMCP(
    "MoreTea Robot Control",
    instructions=(
        "Robot-side control server for MoreTea. "
        "Use health to verify ROS readiness, express_emotion to change the robot eyes, "
        "capture_image to fetch the latest buffered camera frame, get_recognized_faces to inspect the latest face-recognition snapshot, "
        "register_face to save a newly met person's face through the robot-side face registration service, "
        "list_tour_stops to inspect known tour locations, start_navigation_to_stop to begin one stop navigation action, "
        "get_navigation_action_status to inspect one navigation action, navigate_to_stop only as a temporary compatibility wrapper, "
        "cancel_navigation to halt an active navigation task, and get_navigation_status to inspect Nav2 state."
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
def capture_image(ctx: Context[ServerSession, AppContext]) -> dict[str, object]:
    """Return the latest buffered camera frame as a base64-encoded JPEG."""
    try:
        return ctx.request_context.lifespan_context.camera.capture_image()
    except RuntimeError as exc:
        return _error_payload(str(exc))


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


@mcp.tool()
def navigate_to_stop(stop_id: str, ctx: Context[ServerSession, AppContext]) -> dict[str, object]:
    """Compatibility wrapper that blocks until one configured tour stop finishes navigating."""
    lifespan = ctx.request_context.lifespan_context
    target = next((stop for stop in lifespan.tour_stops if stop.id == stop_id.strip()), None)
    if target is None:
        available = [stop.id for stop in lifespan.tour_stops]
        return _error_payload(
            f"Unknown stop_id '{stop_id}'.",
            stop_id=stop_id,
            available_stop_ids=available,
        )
    return lifespan.tour_navigation.navigate_to_stop(target)


@mcp.tool()
def start_navigation_to_stop(
    stop_id: str,
    ctx: Context[ServerSession, AppContext],
    session_id: str | None = None,
    turn_id: str | None = None,
) -> dict[str, object]:
    """Start one Humble Nav2 navigation action for a configured tour stop."""
    lifespan = ctx.request_context.lifespan_context
    target = next((stop for stop in lifespan.tour_stops if stop.id == stop_id.strip()), None)
    if target is None:
        available = [stop.id for stop in lifespan.tour_stops]
        return _error_payload(
            f"Unknown stop_id '{stop_id}'.",
            stop_id=stop_id,
            available_stop_ids=available,
        )
    return lifespan.tour_navigation.start_navigation_to_stop(
        target,
        session_id=session_id,
        turn_id=turn_id,
    )


@mcp.tool()
def get_navigation_action_status(action_id: str, ctx: Context[ServerSession, AppContext]) -> dict[str, object]:
    """Inspect one navigation action by action_id."""
    return ctx.request_context.lifespan_context.tour_navigation.get_navigation_action_status(action_id)


@mcp.tool()
def cancel_navigation(
    ctx: Context[ServerSession, AppContext],
    action_id: str | None = None,
) -> dict[str, object]:
    """Cancel any active Humble Nav2 navigation started through this server."""
    return ctx.request_context.lifespan_context.tour_navigation.cancel_navigation(action_id=action_id)


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
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
