from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_skill_docs_and_index_reference_only_supported_tools_and_resources() -> None:
    server_path = ROOT / "apps" / "mcp-server" / "src" / "mission_control_mcp_server" / "server.py"
    resources_path = ROOT / "plugins" / "mission-control" / "mcp" / "resources.json"
    doc_paths = [
        ROOT / "plugins" / "mission-control" / "SKILL_INDEX.md",
        ROOT / "plugins" / "mission-control" / "skills" / "mission-control-evals-observability" / "SKILL.md",
        ROOT / "plugins" / "mission-control" / "skills" / "mission-control-import" / "SKILL.md",
    ]

    server_text = server_path.read_text(encoding="utf-8")
    exposed_tools = set(re.findall(r"\"(mission_control_[a-z0-9_]+)\"\s*:", server_text))
    exposed_resources = {
        item["uri_template"]
        for item in json.loads(resources_path.read_text(encoding="utf-8"))["resources"]
    }

    for path in doc_paths:
        text = path.read_text(encoding="utf-8")
        referenced_tools = set(re.findall(r"`(mission_control_[a-z0-9_]+)`", text))
        referenced_resources = set(re.findall(r"`(mission-control://[^`]+)`", text))

        assert referenced_tools <= exposed_tools, f"Unsupported tool reference in {path}"
        assert referenced_resources <= exposed_resources, f"Unsupported resource reference in {path}"
