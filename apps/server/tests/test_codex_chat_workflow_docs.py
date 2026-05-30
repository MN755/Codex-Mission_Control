from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
DOC_PATH = ROOT / "docs" / "CODEX_CHAT_WORKFLOWS.md"
EXAMPLES_DIR = ROOT / "examples" / "codex-chat-workflows"


def test_codex_chat_workflows_doc_lists_every_shipped_example() -> None:
    doc = DOC_PATH.read_text(encoding="utf-8")
    example_names = sorted(path.name for path in EXAMPLES_DIR.glob("*.md"))
    for example_name in example_names:
        assert example_name in doc, f"{example_name} is missing from {DOC_PATH}"
