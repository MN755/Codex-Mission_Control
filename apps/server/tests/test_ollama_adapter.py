from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path


ADAPTER_PATH = Path(__file__).resolve().parents[3] / "scripts" / "ollama_adapter.py"
SPEC = importlib.util.spec_from_file_location("mission_control_ollama_adapter", ADAPTER_PATH)
assert SPEC and SPEC.loader
ollama_adapter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ollama_adapter)


def test_select_model_prefers_stronger_local_coding_model(monkeypatch) -> None:
    monkeypatch.setattr(
        ollama_adapter,
        "_list_models",
        lambda: ["qwen2.5:7b", "llama3:latest", "gpt-oss:20b"],
    )
    assert ollama_adapter._select_model("qwen2.5:7b") == "gpt-oss:20b"


def test_repair_reason_requires_edits_for_claimed_fix() -> None:
    prompt = 'Editing expected for this task: yes\n{"report": {}, "edits": []}'
    text = """
    {
      "report": {
        "agent": "Service Flow Builder",
        "task_id": "2",
        "status": "done",
        "summary": "Fixed the failing add function.",
        "files_changed": [],
        "tests_run": [],
        "blockers": [],
        "risks": [],
        "recommended_next_task": "Run validation."
      },
      "edits": []
    }
    """
    reason = ollama_adapter._repair_reason(prompt, text)
    assert reason is not None
    assert "claimed a finished code change" in reason.lower()


def test_repair_reason_rejects_file_change_claim_for_non_edit_task() -> None:
    prompt = 'Editing expected for this task: no\n{"report": {}, "edits": []}'
    text = """
    {
      "report": {
        "agent": "Validation Specialist",
        "task_id": "1",
        "status": "done",
        "summary": "Updated src/math_utils.py while reproducing the failure.",
        "files_changed": ["src/math_utils.py"],
        "tests_run": ["pytest tests/test_math_utils.py"],
        "blockers": [],
        "risks": [],
        "recommended_next_task": "Implement the smallest safe code fix."
      },
      "edits": []
    }
    """
    reason = ollama_adapter._repair_reason(prompt, text)
    assert reason is not None
    assert "non-editing" in reason.lower()


def test_main_falls_back_to_next_model_after_failed_repairs(monkeypatch, capsys) -> None:
    calls: list[str] = []

    def fake_generate(model: str, prompt: str) -> str:
        calls.append(model)
        if model == "bad-model":
            return '{"report":{"status":"done","summary":"Fixed it.","files_changed":["src/math_utils.py"]},"edits":[]}'
        return json.dumps(
            {
                "report": {
                    "agent": "Service Flow Builder",
                    "task_id": "2",
                    "status": "done",
                    "summary": "Fixed the add function.",
                    "files_changed": ["src/math_utils.py"],
                    "tests_run": ["pytest tests/test_math_utils.py"],
                    "blockers": [],
                    "risks": [],
                    "recommended_next_task": "Re-run focused validation.",
                },
                "edits": [
                    {
                        "path": "src/math_utils.py",
                        "content": "def add(a, b):\n    return a + b\n",
                    }
                ],
            }
        )

    monkeypatch.setattr(ollama_adapter, "_candidate_models", lambda _requested: ["bad-model", "good-model"])
    monkeypatch.setattr(ollama_adapter, "_generate", fake_generate)
    monkeypatch.setattr(
        ollama_adapter.sys,
        "stdin",
        io.StringIO('Editing expected for this task: yes\n{"report": {}, "edits": []}'),
    )

    exit_code = ollama_adapter.main()
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert calls[:4] == ["bad-model", "bad-model", "bad-model", "bad-model"]
    assert "good-model" in calls
    assert '"path": "src/math_utils.py"' in payload["result"]
