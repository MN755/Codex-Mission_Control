from __future__ import annotations

import json
import subprocess
from pathlib import Path

from manager import service
from models import Project
from workspace_tooling import detect_workspace_tooling


def test_detect_workspace_tooling_summarizes_repo_native_helpers(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname='demo'\n[tool.ruff]\nline-length = 100\n",
        encoding="utf-8",
    )
    (tmp_path / "uv.lock").write_text("version = 1\n", encoding="utf-8")
    (tmp_path / ".pre-commit-config.yaml").write_text("repos: []\n", encoding="utf-8")
    (tmp_path / "noxfile.py").write_text("import nox\n", encoding="utf-8")
    (tmp_path / "package.json").write_text(
        json.dumps({"devDependencies": {"@playwright/test": "^1.55.0"}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "workspace_tooling._which",
        lambda command: f"C:/tools/{command}.exe" if command in {"uv", "ruff", "pre-commit", "rg", "gitleaks"} else None,
    )

    payload = detect_workspace_tooling(tmp_path, project_name="Demo")

    assert payload["available"] is True
    assert payload["repo_profile"]["python_repo"] is True
    assert payload["repo_profile"]["node_repo"] is True
    assert "uv run pytest" in payload["validation_commands"]
    assert "pre-commit run --all-files" in payload["validation_commands"]
    assert "gitleaks dir . --redact" in payload["security_commands"]
    assert "rg --files" in payload["intake_commands"]
    tools = {tool["id"]: tool for tool in payload["tools"]}
    assert tools["ruff"]["configured"] is True
    assert tools["ruff"]["installed"] is True
    assert tools["playwright"]["configured"] is True
    assert tools["playwright"]["installed"] is False
    packs = {pack["id"]: pack for pack in payload["packs"]}
    assert packs["validation_evidence_pack"]["status"] == "needs_setup"
    assert "Install OSV-Scanner" in " ".join(payload["recommended_next_steps"])


def test_search_codebase_uses_ripgrep_when_available(monkeypatch, tmp_path: Path) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    project = Project(id=7, name="Demo", workspace_path=str(workspace), source_path=str(workspace))

    monkeypatch.setattr("manager.shutil.which", lambda command: "C:/tools/rg.exe" if command == "rg" else None)

    class Result:
        returncode = 0
        stdout = "src/main.py:3:TODO wire validation lane\nREADME.md:9:TODO add docs\n"

    monkeypatch.setattr("manager.subprocess.run", lambda *args, **kwargs: Result())

    payload = service.search_codebase(project, pattern="TODO", glob="*.py", max_matches=2)

    assert payload["search_backend"] == "ripgrep"
    assert payload["match_count"] == 2
    assert payload["matches"][0]["path"] == "src/main.py"
    assert payload["truncated"] is False


def test_search_codebase_falls_back_without_ripgrep(monkeypatch, tmp_path: Path) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    (workspace / "app.py").write_text("print('alpha')\n# TODO ship\n", encoding="utf-8")
    project = Project(id=8, name="Fallback", workspace_path=str(workspace), source_path=str(workspace))

    monkeypatch.setattr("manager.shutil.which", lambda command: None)

    payload = service.search_codebase(project, pattern="TODO", max_matches=5)

    assert payload["search_backend"] == "python"
    assert payload["match_count"] == 1
    assert payload["matches"][0]["path"] == "app.py"
    assert "fell back" in " ".join(payload["notes"]).lower()
