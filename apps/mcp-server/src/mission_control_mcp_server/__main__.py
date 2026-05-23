from __future__ import annotations

import asyncio
import json
import sys
from typing import Any

from mission_control_mcp_server.server import MissionControlMcpServer


def _read_message(stream: Any) -> dict[str, Any] | None:
    while True:
        raw = stream.readline()
        if not raw:
            return None
        line = raw.strip()
        if not line:
            continue
        return json.loads(line.decode("utf-8"))


def _write_message(stream: Any, payload: dict[str, Any]) -> None:
    encoded = json.dumps(payload, default=str).encode("utf-8")
    stream.write(encoded + b"\n")
    stream.flush()


async def _run() -> None:
    server = MissionControlMcpServer()
    stdin = sys.stdin.buffer
    stdout = sys.stdout.buffer
    while True:
        try:
            request = _read_message(stdin)
        except (ValueError, json.JSONDecodeError) as exc:
            response = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": f"Invalid JSON-RPC payload: {exc}"},
            }
            _write_message(stdout, response)
            continue
        if request is None:
            return
        response = await server.handle_request(request)
        if response is None:
            continue
        _write_message(stdout, response)


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
