from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
ENTRYPOINT = ROOT / "scripts" / "serve-mission-control-mcp.py"


def _read_line(stream) -> dict:
    raw = stream.readline()
    assert raw, "unexpected EOF while reading MCP stdout"
    return json.loads(raw.decode("utf-8"))


def test_stdio_entrypoint_speaks_newline_delimited_json_rpc() -> None:
    process = subprocess.Popen(
        [sys.executable, str(ENTRYPOINT)],
        cwd=str(ROOT),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        assert process.stdin is not None
        assert process.stdout is not None
        initialize = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2025-03-26", "clientInfo": {"name": "pytest", "version": "0"}, "capabilities": {}},
        }
        process.stdin.write((json.dumps(initialize) + "\n").encode("utf-8"))
        process.stdin.flush()
        init_response = _read_line(process.stdout)
        assert init_response["id"] == 1
        assert init_response["result"]["serverInfo"]["name"] == "mission-control"
        assert init_response["result"]["capabilities"]["tools"]["listChanged"] is False

        initialized = {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}
        process.stdin.write((json.dumps(initialized) + "\n").encode("utf-8"))
        process.stdin.flush()

        tools_list = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
        process.stdin.write((json.dumps(tools_list) + "\n").encode("utf-8"))
        process.stdin.flush()
        tools_response = _read_line(process.stdout)
        tool_names = {item["name"] for item in tools_response["result"]["tools"]}
        assert "mission_control_get_status" in tool_names
        assert "mission_control_import_existing_codebase" in tool_names

        templates_list = {"jsonrpc": "2.0", "id": 3, "method": "resources/templates/list", "params": {}}
        process.stdin.write((json.dumps(templates_list) + "\n").encode("utf-8"))
        process.stdin.flush()
        templates_response = _read_line(process.stdout)
        template_names = {item["uriTemplate"] for item in templates_response["result"]["resourceTemplates"]}
        assert "mission-control://projects/{project_id}/status" in template_names
    finally:
        process.terminate()
        process.wait(timeout=10)
