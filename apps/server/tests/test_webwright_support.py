from __future__ import annotations

import json
from pathlib import Path

from db import SessionLocal
from models import Project
from webwright_support import detect_webwright_status

from conftest import sample_workspace


def test_detect_webwright_status_ready(monkeypatch, tmp_path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "package.json").write_text(
        json.dumps({"devDependencies": {"@playwright/test": "^1.52.0"}}),
        encoding="utf-8",
    )
    (workspace / "playwright.config.ts").write_text("export default {}", encoding="utf-8")

    monkeypatch.setattr("webwright_support._which", lambda command: f"C:/tools/{command}.cmd" if command in {"webwright", "playwright"} else None)
    monkeypatch.setattr("webwright_support._has_module", lambda name: name in {"webwright", "playwright"})
    monkeypatch.setattr("webwright_support._module_version", lambda name: "0.1.0" if name == "webwright" else "1.55.0")
    monkeypatch.setattr("webwright_support._run_command", lambda args: (True, "help"))

    payload = detect_webwright_status(workspace_path=workspace, project_name="Demo")

    assert payload["available"] is True
    assert payload["install_status"] == "ready"
    assert payload["launch_command"] == "C:/tools/webwright.cmd"
    assert "Playwright config file detected" in " ".join(payload["workspace_signals"])


def test_detect_webwright_status_missing_runtime_but_workspace_is_browser_shaped(monkeypatch, tmp_path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "tests" / "e2e").mkdir(parents=True, exist_ok=True)
    (workspace / "package.json").write_text(
        json.dumps({"devDependencies": {"@playwright/test": "^1.52.0"}}),
        encoding="utf-8",
    )

    monkeypatch.setattr("webwright_support._which", lambda command: None)
    monkeypatch.setattr("webwright_support._has_module", lambda name: False)
    monkeypatch.setattr("webwright_support._module_version", lambda name: None)

    payload = detect_webwright_status(workspace_path=workspace, project_name="Demo")

    assert payload["available"] is False
    assert payload["install_status"] == "missing"
    assert "Clone the upstream Webwright repository" in str(payload["recommended_fix"])
    assert payload["recommended_install_commands"]


def _seed_project() -> int:
    workspace_root = Path(sample_workspace("webwright-status"))
    workspace_root.mkdir(parents=True, exist_ok=True)

    db = SessionLocal()
    try:
        project = Project(
            name="Webwright Status Project",
            idea="Exercise the project-scoped Webwright readiness endpoint.",
            workspace_path=workspace_root.as_posix(),
            runner_mode="dry_run",
            manager_mode="auto",
        )
        db.add(project)
        db.commit()
        return int(project.id)
    finally:
        db.close()


def test_project_webwright_endpoint_returns_project_scoped_readiness(client, bridge_headers, monkeypatch) -> None:
    project_id = _seed_project()
    monkeypatch.setattr(
        "manager.detect_webwright_status",
        lambda **kwargs: {
            "project_name": "Webwright Status Project",
            "workspace_path": kwargs.get("workspace_path"),
            "available": True,
            "install_status": "ready",
            "cli_detected": True,
            "cli_path": "C:/tools/webwright.cmd",
            "python_package_detected": True,
            "playwright_package_detected": True,
            "playwright_cli_detected": True,
            "version": "0.1.0",
            "launch_command": "webwright",
            "workspace_signals": ["Playwright config file detected in the workspace root."],
            "summary": "Webwright runtime and Playwright package are both detectable from the current Mission Control runtime.",
            "recommended_fix": None,
            "recommended_install_commands": ["git clone https://github.com/microsoft/Webwright"],
            "use_cases": ["Reusable browser scripts."],
            "notes": ["Optional browser-agent companion."],
            "bridge_markdown": "## Mission Control Webwright",
            "details": {"runtime_python": "python"},
        },
    )

    response = client.get(f"/api/projects/{project_id}/webwright", headers=bridge_headers)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["project_id"] == project_id
    assert payload["available"] is True
    assert payload["install_status"] == "ready"
    assert payload["launch_command"] == "webwright"
