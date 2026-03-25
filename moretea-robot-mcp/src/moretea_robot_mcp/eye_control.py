from __future__ import annotations

from typing import Final

EMOTION_MAP: Final[dict[str, int]] = {
    "neutral": 0,
    "happy": 1,
    "sad": 2,
    "angry": 3,
    "confused": 4,
    "shocked": 5,
    "love": 6,
    "shy": 7,
}

SUPPORTED_EMOTIONS: Final[tuple[str, ...]] = tuple(EMOTION_MAP.keys())
EYE_EXPRESSION_TOPIC: Final[str] = "/eye_expression"
EYE_EXPRESSION_TYPE: Final[str] = "std_msgs/msg/Int32"


def normalize_emotion_name(mood: str) -> str:
    return mood.strip().lower()


def resolve_emotion_code(mood: str) -> int:
    normalized = normalize_emotion_name(mood)
    try:
        return EMOTION_MAP[normalized]
    except KeyError as exc:
        supported = ", ".join(SUPPORTED_EMOTIONS)
        raise ValueError(f"Unsupported emotion '{mood}'. Supported emotions: {supported}.") from exc
