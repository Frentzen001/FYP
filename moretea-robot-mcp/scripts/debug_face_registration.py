#!/usr/bin/env python3
"""Standalone diagnostic for the FaceRegistrationProvider.

Run on the robot after sourcing the ROS environment:

    source /opt/ros/humble/setup.bash
    cd /home/<user>/FYP/moretea-robot-mcp
    uv run python scripts/debug_face_registration.py
"""
from __future__ import annotations

import json
import sys
import traceback

print("=" * 60)
print("Face Registration Diagnostic")
print("=" * 60)

# ── 1. Check module-level imports ──────────────────────────────
print("\n[1] Checking module-level imports...")
try:
    from moretea_robot_mcp.face_registration import (
        FACE_REGISTRATION_SERVICE_AVAILABLE,
        ROS2_AVAILABLE,
        FaceRegistrationProvider,
    )
    print(f"  ROS2_AVAILABLE                    : {ROS2_AVAILABLE}")
    print(f"  FACE_REGISTRATION_SERVICE_AVAILABLE: {FACE_REGISTRATION_SERVICE_AVAILABLE}")
except Exception:
    print("  FAILED to import face_registration module:")
    traceback.print_exc()
    sys.exit(1)

if not ROS2_AVAILABLE:
    print("\nERROR: rclpy not importable. Source the ROS 2 Humble environment first.")
    sys.exit(1)

if not FACE_REGISTRATION_SERVICE_AVAILABLE:
    print("\nERROR: face_tracking_interfaces not importable. Source the workspace overlay.")
    sys.exit(1)

# ── 2. Instantiate and start the provider ──────────────────────
print("\n[2] Starting FaceRegistrationProvider...")
provider = FaceRegistrationProvider()
try:
    provider.start()
    print("  start() completed without exception")
except Exception as exc:
    print(f"  start() raised: {exc}")
    traceback.print_exc()

# ── 3. Health check ────────────────────────────────────────────
print("\n[3] health() result:")
h = provider.health()
print(json.dumps(h, indent=2, default=str))

# ── 4. Try to register a face ──────────────────────────────────
print("\n[4] Calling register_face('DebugTest')...")
try:
    result = provider.register_face("DebugTest")
    print("  Result:")
    print(json.dumps(result, indent=2, default=str))
except Exception as exc:
    print(f"  Raised {type(exc).__name__}: {exc}")
    traceback.print_exc()

# ── 5. Cleanup ─────────────────────────────────────────────────
print("\n[5] Shutting down provider...")
try:
    provider.shutdown()
    print("  shutdown() OK")
except Exception as exc:
    print(f"  shutdown() raised: {exc}")

print("\n" + "=" * 60)
print("Diagnostic complete.")
print("=" * 60)
