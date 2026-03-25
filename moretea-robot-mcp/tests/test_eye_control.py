from moretea_robot_mcp.eye_control import EMOTION_MAP, SUPPORTED_EMOTIONS, resolve_emotion_code


def test_supported_emotions_match_robot_contract() -> None:
    assert EMOTION_MAP == {
        "neutral": 0,
        "happy": 1,
        "sad": 2,
        "angry": 3,
        "confused": 4,
        "shocked": 5,
        "love": 6,
        "shy": 7,
    }
    assert SUPPORTED_EMOTIONS == tuple(EMOTION_MAP.keys())


def test_resolve_emotion_code_normalizes_input() -> None:
    assert resolve_emotion_code("  HAPPY ") == 1
    assert resolve_emotion_code("Confused") == 4


def test_resolve_emotion_code_rejects_unknown_values() -> None:
    try:
        resolve_emotion_code("curious")
    except ValueError as exc:
        assert "Unsupported emotion 'curious'" in str(exc)
        assert "neutral" in str(exc)
        assert "shy" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Expected ValueError for unsupported emotion.")
