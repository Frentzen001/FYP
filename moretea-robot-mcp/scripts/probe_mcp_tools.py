#!/usr/bin/env python3
"""Directly call MCP tools on the running robot MCP server and print responses.

Run on the robot (or OpenClaw PC via the SSH tunnel):

    cd ~/FYP/moretea-robot-mcp
    uv run python scripts/probe_mcp_tools.py
    uv run python scripts/probe_mcp_tools.py --url http://127.0.0.1:8765/mcp
    uv run python scripts/probe_mcp_tools.py --register-name DebugTest
"""
from __future__ import annotations

import argparse
import json
import sys
import uuid

try:
    import httpx
except ImportError:
    print("httpx not available. Install it: uv add httpx")
    sys.exit(1)

DEFAULT_URL = "http://127.0.0.1:8765/mcp"


def call_tool(url: str, tool_name: str, arguments: dict) -> dict:
    """Send a single stateless MCP tool-call and return the parsed result."""
    payload = {
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()),
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": arguments},
    }
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    resp = httpx.post(url, json=payload, headers=headers, timeout=15.0)
    resp.raise_for_status()

    # Stateless HTTP returns either plain JSON or SSE; handle both.
    content_type = resp.headers.get("content-type", "")
    if "text/event-stream" in content_type:
        # Extract the JSON-RPC response from the SSE stream
        for line in resp.text.splitlines():
            line = line.strip()
            if line.startswith("data:"):
                return json.loads(line[len("data:"):].strip())
        raise ValueError(f"No data line found in SSE response:\n{resp.text}")
    return resp.json()


def pretty(label: str, data: object) -> None:
    print(f"\n{'─' * 60}")
    print(f"  {label}")
    print(f"{'─' * 60}")
    print(json.dumps(data, indent=2, default=str))


def main() -> None:
    parser = argparse.ArgumentParser(description="Probe the robot MCP server tools directly.")
    parser.add_argument("--url", default=DEFAULT_URL, help="MCP server URL")
    parser.add_argument("--register-name", default=None, metavar="NAME",
                        help="If given, also call register_face with this name")
    args = parser.parse_args()

    url = args.url
    print(f"Probing MCP server at: {url}\n")

    # ── health ────────────────────────────────────────────────────
    print("[1] Calling health ...")
    try:
        resp = call_tool(url, "health", {})
        pretty("health response (raw JSON-RPC)", resp)
        result = resp.get("result", {})
        content = result.get("content", [{}])
        if content and isinstance(content[0], dict):
            tool_result_text = content[0].get("text", "")
            if tool_result_text:
                try:
                    tool_result = json.loads(tool_result_text)
                    pretty("health tool result (parsed)", tool_result)
                    fr = tool_result.get("face_registration_ready")
                    err = tool_result.get("startup_errors", {}).get("face_registration")
                    print(f"\n  face_registration_ready : {fr}")
                    print(f"  startup_error           : {err}")
                except json.JSONDecodeError:
                    print(f"  (raw text): {tool_result_text}")
    except Exception as exc:
        print(f"  FAILED: {exc}")

    # ── register_face ─────────────────────────────────────────────
    if args.register_name:
        name = args.register_name
        print(f"\n[2] Calling register_face(name={name!r}) ...")
        try:
            resp = call_tool(url, "register_face", {"name": name})
            pretty("register_face response (raw JSON-RPC)", resp)
            result = resp.get("result", {})
            content = result.get("content", [{}])
            if content and isinstance(content[0], dict):
                tool_result_text = content[0].get("text", "")
                if tool_result_text:
                    try:
                        tool_result = json.loads(tool_result_text)
                        pretty("register_face tool result (parsed)", tool_result)
                    except json.JSONDecodeError:
                        print(f"  (raw text): {tool_result_text}")
        except Exception as exc:
            print(f"  FAILED: {exc}")

    print("\nDone.")


if __name__ == "__main__":
    main()
