from __future__ import annotations

import math
import os
from dataclasses import dataclass
from pathlib import Path

import yaml


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


DEFAULT_TOUR_STOPS_PATH = _repo_root() / "config" / "tour_stops.yaml"


@dataclass(frozen=True)
class TourStop:
    id: str
    name: str
    aliases: tuple[str, ...]
    x: float
    y: float
    ow: float
    narration: str
    faq_tags: tuple[str, ...] = ()
    escort_only: bool = False


def resolve_tour_stops_path(explicit_path: str | Path | None = None) -> Path:
    if explicit_path is not None:
        return Path(explicit_path)
    configured = os.getenv("MORETEA_TOUR_STOPS_PATH")
    if configured:
        return Path(configured)
    return DEFAULT_TOUR_STOPS_PATH


def normalize_location_candidate(text: str) -> str:
    return " ".join(text.lower().strip().split())


def load_tour_stops(path: str | Path | None = None) -> tuple[TourStop, ...]:
    resolved = resolve_tour_stops_path(path)
    with resolved.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    if not isinstance(raw, dict):
        raise ValueError("tour_stops.yaml must contain a mapping at the top level")
    items = raw.get("stops", [])
    if not isinstance(items, list) or not items:
        raise ValueError("tour_stops.yaml must define at least one stop")

    result: list[TourStop] = []
    seen_ids: set[str] = set()
    seen_names: set[str] = set()
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"stop #{index} must be a mapping")
        for required_key in ("id", "name", "x", "y", "ow", "narration"):
            if required_key not in item:
                raise ValueError(f"stop #{index} is missing required field '{required_key}'")
        stop = TourStop(
            id=str(item["id"]).strip(),
            name=str(item["name"]).strip(),
            aliases=tuple(str(alias).strip() for alias in item.get("aliases", [])),
            x=float(item["x"]),
            y=float(item["y"]),
            ow=float(item["ow"]),
            narration=str(item["narration"]).strip(),
            faq_tags=tuple(str(tag).strip() for tag in item.get("faq_tags", [])),
            escort_only=bool(item.get("escort_only", False)),
        )
        if not stop.id:
            raise ValueError(f"stop #{index} must have a non-empty id")
        if stop.id in seen_ids:
            raise ValueError(f"duplicate stop id: {stop.id}")
        seen_ids.add(stop.id)
        if not stop.name:
            raise ValueError(f"stop '{stop.id}' must have a non-empty name")
        if not stop.narration:
            raise ValueError(f"stop '{stop.id}' must have a non-empty narration")
        for numeric_name, value in (("x", stop.x), ("y", stop.y), ("ow", stop.ow)):
            if not math.isfinite(value):
                raise ValueError(f"stop '{stop.id}' has an invalid {numeric_name} value")
        local_names = {
            normalize_location_candidate(candidate)
            for candidate in (stop.name, stop.id.replace("_", " "), *stop.aliases)
        }
        for normalized in local_names:
            if normalized in seen_names:
                raise ValueError(f"duplicate stop name or alias detected: {normalized}")
        seen_names.update(local_names)
        result.append(stop)
    return tuple(result)


def serialize_stop(stop: TourStop) -> dict[str, object]:
    return {
        "stop_id": stop.id,
        "name": stop.name,
        "aliases": list(stop.aliases),
        "narration": stop.narration,
        "faq_tags": list(stop.faq_tags),
        "escort_only": stop.escort_only,
    }
