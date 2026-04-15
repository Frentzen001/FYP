from __future__ import annotations

import sys
import types

uvicorn_stub = types.ModuleType("uvicorn")
uvicorn_stub.run = lambda *args, **kwargs: None
sys.modules.setdefault("uvicorn", uvicorn_stub)

fastapi_stub = types.ModuleType("fastapi")


class _FastAPI:
    def __init__(self, *args, **kwargs) -> None:
        return

    def get(self, *args, **kwargs):
        def decorator(func):
            return func

        return decorator

    def post(self, *args, **kwargs):
        def decorator(func):
            return func

        return decorator

    def mount(self, *args, **kwargs) -> None:
        return


class _HTTPException(Exception):
    pass


fastapi_stub.FastAPI = _FastAPI
fastapi_stub.HTTPException = _HTTPException
sys.modules.setdefault("fastapi", fastapi_stub)

responses_stub = types.ModuleType("fastapi.responses")
responses_stub.JSONResponse = dict
responses_stub.StreamingResponse = dict
sys.modules.setdefault("fastapi.responses", responses_stub)

staticfiles_stub = types.ModuleType("fastapi.staticfiles")


class _StaticFiles:
    def __init__(self, *args, **kwargs) -> None:
        return


staticfiles_stub.StaticFiles = _StaticFiles
sys.modules.setdefault("fastapi.staticfiles", staticfiles_stub)

import backend


def make_store() -> backend.ObservabilityStore:
    store = backend.ObservabilityStore()
    store._state = {
        "generated_at": backend._utc_now(),
        "current_turn_id": None,
        "latest_robot_snapshot": None,
        "machines": [],
        "links": [],
        "turns": [],
    }
    store._machine_index = {}
    store._link_index = {}
    store._turn_index = {}
    store._timeline_events.clear()
    return store
