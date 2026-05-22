from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


def _discover_repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _configure_import_path(repo_root: Path) -> None:
    server_src = repo_root / "apps" / "server" / "src"
    mcp_src = repo_root / "apps" / "mcp-server" / "src"
    if str(server_src) not in sys.path:
        sys.path.insert(0, str(server_src))
    if str(mcp_src) not in sys.path:
        sys.path.insert(0, str(mcp_src))


def _json_dump(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, default=str)


def _start_daemon(repo_root: Path, *, host: str | None, port: int | None) -> tuple[bool, str]:
    script_path = repo_root / "scripts" / "start-mission-control-daemon.ps1"
    if not script_path.exists():
        return False, f"Missing daemon start script: {script_path}"
    powershell = "powershell.exe" if os.name == "nt" else "pwsh"
    command = [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script_path)]
    if port is not None:
        command.extend(["-BackendPort", str(port)])
    if host:
        command.extend(["-BindHost", host])
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=90, check=False)
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"
    output = completed.stdout.strip() or completed.stderr.strip()
    return completed.returncode == 0, output or "Daemon start completed."


def _wait_for_backend(base_url: str, *, timeout: float = 20.0) -> bool:
    import urllib.request

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{base_url}/api/health", timeout=2.0) as response:
                if response.status == 200:
                    return True
        except Exception:
            time.sleep(0.5)
    return False


def _mcp_check(repo_root: Path, *, base_url: str) -> dict[str, Any]:
    plugin_manifest = repo_root / "plugins" / "mission-control" / "plugin.json"
    example_config = repo_root / "plugins" / "mission-control" / "mcp" / "mission-control-mcp.example.json"
    repo_local_bundle = repo_root / ".codex" / "plugins" / "mission-control" / "plugin.json"
    local_skills = repo_root / ".codex" / "skills"
    mcp_package = repo_root / "apps" / "mcp-server" / "src" / "mission_control_mcp_server" / "__main__.py"
    missing = [
        str(path.relative_to(repo_root))
        for path in [plugin_manifest, example_config, repo_local_bundle, local_skills, mcp_package]
        if not path.exists()
    ]
    status = "ready" if not missing else "degraded"
    payload = {
        "status": status,
        "plugin_manifest": str(plugin_manifest),
        "example_config": str(example_config),
        "repo_local_plugin_manifest": str(repo_local_bundle),
        "local_skills_path": str(local_skills),
        "mcp_package_entrypoint": str(mcp_package),
        "missing_assets": missing,
        "recommended_codex_mcp_command": "python -m mission_control_mcp_server",
        "notes": [
            "Mission Control MCP uses stdio and is normally launched by Codex, not as a standalone public service.",
            "This check validates local bridge assets and attempts one protected Mission Control MCP tool call.",
        ],
    }
    try:
        from mission_control_mcp_server.client import MissionControlDaemonClient
        from mission_control_mcp_server.server import MissionControlMcpServer

        client = MissionControlDaemonClient(base_url=base_url)
        server = MissionControlMcpServer(client=client)
        tool_result = server.call_tool("mission_control_plugin_health", {})
        payload["authenticated_tool_call"] = {
            "status": "ready",
            "summary": "Protected Mission Control MCP tool call succeeded.",
            "result_preview": tool_result.get("structuredContent", {}),
        }
    except Exception as exc:  # noqa: BLE001
        payload["authenticated_tool_call"] = {
            "status": "degraded",
            "summary": f"Protected Mission Control MCP tool call failed: {type(exc).__name__}: {exc}",
        }
        if payload["status"] == "ready":
            payload["status"] = "degraded"
    payload["codex_chat_markdown"] = "\n".join(
        [
            "## Mission Control MCP Bridge Check",
            "",
            f"**Status:** {str(payload['status']).title()}",
            f"**Plugin manifest:** {'Present' if plugin_manifest.exists() else 'Missing'}",
            f"**Repo-local plugin bundle:** {'Present' if repo_local_bundle.exists() else 'Missing'}",
            f"**MCP package entrypoint:** {'Present' if mcp_package.exists() else 'Missing'}",
            f"**Local skills path:** {'Present' if local_skills.exists() else 'Missing'}",
            f"**Protected tool call:** {payload['authenticated_tool_call']['status'].title()}",
        ]
    )
    return payload


def _print_payload(payload: dict[str, Any], *, as_json: bool, markdown_key: str = "codex_chat_markdown") -> None:
    if as_json:
        print(_json_dump(payload))
        return
    print(payload.get(markdown_key) or _json_dump(payload))


def main() -> int:
    parser = argparse.ArgumentParser(description="Bootstrap or inspect Mission Control headless mode.")
    parser.add_argument("--workspace-path", default=None)
    parser.add_argument("--install-path", default=None)
    parser.add_argument("--runtime-path", default=None)
    parser.add_argument("--daemon-host", default=None)
    parser.add_argument("--daemon-port", type=int, default=None)
    parser.add_argument("--mcp-transport", default="stdio")
    parser.add_argument("--mcp-port", type=int, default=None)
    parser.add_argument("--headless-only", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--repair", action="store_true")
    parser.add_argument("--health-check-only", action="store_true")
    parser.add_argument("--mcp-check-only", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    repo_root = Path(args.install_path).expanduser().resolve() if args.install_path else _discover_repo_root()
    _configure_import_path(repo_root)

    try:
        from bootstrap.environment_probe import probe_environment
        from bootstrap.runner_autowire import autowire_headless, get_headless_health, repair_headless
        from config import DEFAULT_BACKEND_HOST, DEFAULT_BACKEND_PORT
    except Exception as exc:  # noqa: BLE001
        message = (
            "Mission Control bootstrap could not import the server runtime. "
            "Install backend dependencies first, for example with `python -m pip install -e .[dev]` from `apps/server`.\n"
            f"Import error: {type(exc).__name__}: {exc}"
        )
        print(message)
        return 1

    host = args.daemon_host or DEFAULT_BACKEND_HOST
    port = args.daemon_port or DEFAULT_BACKEND_PORT
    base_url = f"http://{host}:{port}"

    if args.mcp_check_only:
        daemon_message = None
        if not args.dry_run:
            started, daemon_message = _start_daemon(repo_root, host=host, port=port)
            if not started:
                print(daemon_message)
            elif not _wait_for_backend(base_url):
                print(f"Mission Control daemon did not answer health checks at {base_url}.")
        payload = _mcp_check(repo_root, base_url=base_url)
        if daemon_message:
            payload["daemon_start_message"] = daemon_message
        _print_payload(payload, as_json=args.json)
        return 0 if payload["status"] == "ready" and payload.get("authenticated_tool_call", {}).get("status") == "ready" else 1

    if args.health_check_only:
        payload = asyncio.run(get_headless_health())
        _print_payload(payload, as_json=args.json)
        return 0 if payload["status"] in {"ready", "degraded"} else 1

    daemon_message = None
    if not args.dry_run:
        started, daemon_message = _start_daemon(repo_root, host=host, port=port)
        if not started:
            print(daemon_message)
        elif not _wait_for_backend(base_url):
            print(f"Mission Control daemon did not answer health checks at {base_url}.")

    if args.repair:
        report = asyncio.run(
            repair_headless(
                workspace_path=args.workspace_path,
                install_path=str(repo_root),
                runtime_path=args.runtime_path,
                daemon_host=host,
                daemon_port=port,
                mcp_transport=args.mcp_transport,
                mcp_port=args.mcp_port,
                headless_only=True,
                preserve_config=True,
            )
        )
    else:
        report = asyncio.run(
            autowire_headless(
                workspace_path=args.workspace_path,
                install_path=str(repo_root),
                runtime_path=args.runtime_path,
                daemon_host=host,
                daemon_port=port,
                mcp_transport=args.mcp_transport,
                mcp_port=args.mcp_port,
                headless_only=True,
                dry_run=args.dry_run,
            )
        )

    payload = {
        "install_report": report,
        "environment": probe_environment(
            workspace_path=args.workspace_path,
            install_path=str(repo_root),
            runtime_path=args.runtime_path,
        ),
        "daemon_start_message": daemon_message,
    }
    payload.update(report)
    _print_payload(payload, as_json=args.json)
    return 0 if report["status"] in {"ready", "degraded"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
