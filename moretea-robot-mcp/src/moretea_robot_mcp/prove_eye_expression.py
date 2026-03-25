from __future__ import annotations

import argparse
import sys

from .eye_control import EYE_EXPRESSION_TOPIC, resolve_emotion_code
from .ros_eye_publisher import EyeExpressionPublisher


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Publish one eye-expression message over ROS 2.")
    parser.add_argument("mood", help="Emotion name to publish.")
    parser.add_argument("--topic", default=EYE_EXPRESSION_TOPIC, help="ROS topic to publish to.")
    parser.add_argument(
        "--wait-seconds",
        default=0.25,
        type=float,
        help="How long to wait after queueing the message before exiting.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    code = resolve_emotion_code(args.mood)

    publisher = EyeExpressionPublisher(topic=args.topic)
    try:
        publisher.start()
        publisher.publish_code_once(code, wait_seconds=args.wait_seconds)
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    finally:
        publisher.shutdown()

    print(f"published mood={args.mood.strip().lower()} code={code} topic={args.topic}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
