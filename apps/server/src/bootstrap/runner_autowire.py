from __future__ import annotations

from typing import Any

from bootstrap.environment_probe import probe_environment
from bootstrap.headless_config import build_headless_config, read_headless_config, write_headless_config
from bootstrap.install_report import build_install_report
from bootstrap.runner_probe import summarize_runner_status
from plugin_health import mission_control_plugin_health


async def _install_report(
    *,
    workspace_path: str | None = None,
    install_path: str | None = None,
    runtime_path: str | None = None,
    daemon_host: str | None = None,
    daemon_port: int | None = None,
    mcp_transport: str | None = None,
    mcp_port: int | None = None,
    headless_only: bool = True,
    write_config: bool = True,
    preserve_config: bool = True,
) -> dict[str, Any]:
    runner_summary = summarize_runner_status()
    probes = list(runner_summary["runners"])
    existing = read_headless_config(runtime_path) if preserve_config else None
    config_payload = build_headless_config(
        probes=probes,
        install_path=install_path,
        runtime_path=runtime_path,
        daemon_host=daemon_host,
        daemon_port=daemon_port,
        mcp_transport=mcp_transport,
        mcp_port=mcp_port,
        headless_only=headless_only,
        existing=existing,
    )
    if write_config:
        write_headless_config(config_payload, runtime_path)
    health = await mission_control_plugin_health()
    environment = probe_environment(workspace_path=workspace_path, install_path=install_path, runtime_path=runtime_path)
    return build_install_report(
        probes=probes,
        headless_config=config_payload,
        health=health,
        environment=environment,
    )


async def get_headless_health() -> dict[str, Any]:
    return await mission_control_plugin_health()


def get_headless_config(*, runtime_path: str | None = None) -> dict[str, Any]:
    existing = read_headless_config(runtime_path)
    if existing:
        return existing
    runner_summary = summarize_runner_status()
    payload = build_headless_config(
        probes=list(runner_summary["runners"]),
        install_path=None,
        runtime_path=runtime_path,
        daemon_host=None,
        daemon_port=None,
        mcp_transport=None,
        mcp_port=None,
        headless_only=True,
        existing=None,
    )
    return payload


async def autowire_headless(
    *,
    workspace_path: str | None = None,
    install_path: str | None = None,
    runtime_path: str | None = None,
    daemon_host: str | None = None,
    daemon_port: int | None = None,
    mcp_transport: str | None = None,
    mcp_port: int | None = None,
    headless_only: bool = True,
    dry_run: bool = False,
) -> dict[str, Any]:
    return await _install_report(
        workspace_path=workspace_path,
        install_path=install_path,
        runtime_path=runtime_path,
        daemon_host=daemon_host,
        daemon_port=daemon_port,
        mcp_transport=mcp_transport,
        mcp_port=mcp_port,
        headless_only=headless_only,
        write_config=not dry_run,
        preserve_config=True,
    )


async def repair_headless(
    *,
    workspace_path: str | None = None,
    install_path: str | None = None,
    runtime_path: str | None = None,
    daemon_host: str | None = None,
    daemon_port: int | None = None,
    mcp_transport: str | None = None,
    mcp_port: int | None = None,
    headless_only: bool = True,
    preserve_config: bool = True,
) -> dict[str, Any]:
    return await _install_report(
        workspace_path=workspace_path,
        install_path=install_path,
        runtime_path=runtime_path,
        daemon_host=daemon_host,
        daemon_port=daemon_port,
        mcp_transport=mcp_transport,
        mcp_port=mcp_port,
        headless_only=headless_only,
        write_config=True,
        preserve_config=preserve_config,
    )


def get_install_doctor_snapshot(*, workspace_path: str | None = None) -> dict[str, Any]:
    environment = probe_environment(workspace_path=workspace_path)
    config_payload = get_headless_config()
    runner_summary = summarize_runner_status()
    return {
        "environment": environment,
        "headless_config": config_payload,
        "runner_status": runner_summary,
        "redaction_status": "redacted" if environment.get("path_entries_summary", {}).get("entries") else "clean",
    }
