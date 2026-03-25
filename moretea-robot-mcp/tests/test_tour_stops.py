from pathlib import Path

import pytest

from moretea_robot_mcp.tour_stops import load_tour_stops, serialize_stop


def test_load_tour_stops_reads_default_catalog() -> None:
    stops = load_tour_stops()

    assert len(stops) >= 2
    assert stops[0].id == "entrance"
    assert any(stop.id == "exit" for stop in stops)


def test_load_tour_stops_rejects_duplicate_aliases(tmp_path: Path) -> None:
    path = tmp_path / "tour_stops.yaml"
    path.write_text(
        """
stops:
  - id: one
    name: One
    aliases: ["shared"]
    x: 0
    y: 0
    ow: 1
    narration: "A"
  - id: two
    name: Two
    aliases: ["shared"]
    x: 1
    y: 1
    ow: 1
    narration: "B"
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="duplicate stop name or alias"):
        load_tour_stops(path)


def test_serialize_stop_exposes_openclaw_facing_fields_only() -> None:
    stop = load_tour_stops()[0]

    payload = serialize_stop(stop)

    assert payload["stop_id"] == stop.id
    assert payload["name"] == stop.name
    assert "aliases" in payload
    assert "narration" in payload
    assert "x" not in payload
