from __future__ import annotations

from pathlib import Path

import pytest

from imported_codebase import import_service


pytestmark = pytest.mark.no_db_reset


def test_scan_payload_uses_repo_relative_metadata_paths(tmp_path) -> None:
    root = tmp_path / "repo"
    (root / "docs").mkdir(parents=True, exist_ok=True)
    (root / ".github" / "workflows").mkdir(parents=True, exist_ok=True)
    (root / "deploy").mkdir(parents=True, exist_ok=True)
    (root / "src").mkdir(parents=True, exist_ok=True)
    (root / "README.md").write_text("# Repo\n", encoding="utf-8")
    (root / "docs" / "guide.md").write_text("# Guide\n", encoding="utf-8")
    (root / ".github" / "workflows" / "ci.yml").write_text("name: ci\n", encoding="utf-8")
    (root / "deploy" / "Dockerfile").write_text("FROM python:3.12\n", encoding="utf-8")
    (root / ".env").write_text("SECRET=value\n", encoding="utf-8")

    payload = import_service._build_scan_payload(root, depth="standard")

    assert "README.md" in payload["docs_json"]
    assert "docs/guide.md" in payload["docs_json"]
    assert ".github/workflows/ci.yml" in payload["ci_config_json"]
    assert "deploy/Dockerfile" in payload["deployment_config_json"]
    assert any(flag.endswith(".env") for flag in payload["risk_flags_json"])
    assert all(str(root).replace("\\", "/") not in item for item in payload["docs_json"])
