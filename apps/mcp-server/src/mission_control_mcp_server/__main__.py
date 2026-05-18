from __future__ import annotations

import asyncio
import json
import sys

from mission_control_mcp_server.server import MissionControlMcpServer


async def _run() -> None:
    server = MissionControlMcpServer()
    for raw in sys.stdin:
        line = raw.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError as exc:
            response = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": f"Invalid JSON: {exc}"},
            }
        else:
            response = await server.handle_request(request)
        sys.stdout.write(json.dumps(response, default=str) + "\n")
        sys.stdout.flush()


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
