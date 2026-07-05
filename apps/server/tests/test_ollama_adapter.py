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


def test_select_model_honors_strict_requested_model(monkeypatch) -> None:
    monkeypatch.setenv("MISSION_CONTROL_STRICT_MODEL", "1")
    monkeypatch.setattr(
        ollama_adapter,
        "_list_models",
        lambda: ["qwen2.5:7b", "gpt-oss:20b"],
    )

    assert ollama_adapter._select_model("qwen2.5-coder:7b") == "qwen2.5-coder:7b"
    assert ollama_adapter._candidate_models("qwen2.5-coder:7b") == ["qwen2.5-coder:7b"]


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


def test_repair_reason_accepts_search_replace_edit_for_claimed_fix() -> None:
    prompt = 'Editing expected for this task: yes\n{"report": {}, "edits": []}'
    text = """
    {
      "report": {
        "agent": "Service Flow Builder",
        "task_id": "2",
        "status": "done",
        "summary": "Adjusted the ordering logic with a surgical patch.",
        "files_changed": ["django/db/models/sql/compiler.py"],
        "tests_run": [],
        "blockers": [],
        "risks": [],
        "recommended_next_task": "Run validation."
      },
      "edits": [
        {
          "path": "django/db/models/sql/compiler.py",
          "search": "without_ordering = self.ordering_parts.search(sql).group(1)",
          "replace": "without_ordering = self.ordering_parts.search(sql_oneline).group(1)"
        }
      ]
    }
    """
    reason = ollama_adapter._repair_reason(prompt, text)
    assert reason is None


def test_repair_reason_normalizes_common_edit_field_synonyms() -> None:
    prompt = 'Editing expected for this task: yes\n{"report": {}, "edits": []}'
    text = """
    {
      "report": {
        "agent": "Service Flow Builder",
        "task_id": "2",
        "status": "done",
        "summary": "Adjusted the ordering logic with a surgical patch.",
        "files_changed": ["django/db/models/sql/compiler.py"],
        "tests_run": [],
        "blockers": [],
        "risks": [],
        "recommended_next_task": "Run validation."
      },
      "edits": [
        {
          "file": "django/db/models/sql/compiler.py",
          "find": "without_ordering = self.ordering_parts.search(sql).group(1)",
          "replacement": "without_ordering = self.ordering_parts.search(sql_oneline).group(1)"
        }
      ]
    }
    """

    reason = ollama_adapter._repair_reason(prompt, text)

    assert reason is None


def test_repair_reason_infers_single_changed_file_path_for_synonym_edit_payload() -> None:
    prompt = 'Editing expected for this task: yes\n{"report": {}, "edits": []}'
    text = """
    {
      "report": {
        "agent": "Service Flow Builder",
        "task_id": "2",
        "status": "done",
        "summary": "Adjusted the ordering logic with a surgical patch.",
        "files_changed": ["django/db/models/sql/compiler.py"],
        "tests_run": [],
        "blockers": [],
        "risks": [],
        "recommended_next_task": "Run validation."
      },
      "edits": [
        {
          "old_text": "without_ordering = self.ordering_parts.search(sql).group(1)",
          "new_text": "without_ordering = self.ordering_parts.search(sql_oneline).group(1)"
        }
      ]
    }
    """

    reason = ollama_adapter._repair_reason(prompt, text)

    assert reason is None


def test_repair_reason_rejects_placeholder_full_file_edit() -> None:
    prompt = 'Editing expected for this task: yes\n{"report": {}, "edits": []}'
    text = """
    {
      "report": {
        "agent": "Service Flow Builder",
        "task_id": "2",
        "status": "done",
        "summary": "Fixed the ordering bug.",
        "files_changed": ["django/db/models/sql/compiler.py"],
        "tests_run": [],
        "blockers": [],
        "risks": [],
        "recommended_next_task": "Re-run focused validation."
      },
      "edits": [
        {
          "path": "django/db/models/sql/compiler.py",
          "content": "class SQLCompiler:\\n    # ... (other code omitted)\\n"
        }
      ]
    }
    """

    reason = ollama_adapter._repair_reason(prompt, text)

    assert reason is not None
    assert "placeholders" in reason.lower() or "omitted-code" in reason.lower()


def test_repair_reason_rejects_placeholder_replace_block() -> None:
    prompt = 'Editing expected for this task: yes\n{"report": {}, "edits": []}'
    text = """
    {
      "report": {
        "agent": "Service Flow Builder",
        "task_id": "2",
        "status": "done",
        "summary": "Fixed the ordering bug.",
        "files_changed": ["django/db/models/sql/compiler.py"],
        "tests_run": [],
        "blockers": [],
        "risks": [],
        "recommended_next_task": "Re-run focused validation."
      },
      "edits": [
        {
          "path": "django/db/models/sql/compiler.py",
          "search": "without_ordering = self.ordering_parts.search(sql).group(1)",
          "replace": "sql_oneline = ' '.join(sql.split('\\\\n'))\\n# ...\\nwithout_ordering = self.ordering_parts.search(sql_oneline).group(1)"
        }
      ]
    }
    """

    reason = ollama_adapter._repair_reason(prompt, text)

    assert reason is not None
    assert "replacement" in reason.lower() or "placeholders" in reason.lower()


def test_coerce_non_editing_contract_violation_preserves_test_evidence() -> None:
    prompt = 'Editing expected for this task: no\n{"report": {}, "edits": []}'
    text = """
    {
      "report": {
        "agent": "Validation Specialist",
        "task_id": "1",
        "status": "done",
        "summary": "Updated src/math_utils.py while reproducing the failure.",
        "files_changed": ["src/math_utils.py"],
        "tests_run": ["pytest tests/test_math_utils.py -q"],
        "blockers": ["Observed the target test failure."],
        "risks": [],
        "recommended_next_task": "Implement the smallest safe code fix."
      },
      "edits": []
    }
    """

    coerced = ollama_adapter._coerce_non_editing_contract_violation(
        prompt,
        text,
        "This task was marked as non-editing, so do not claim to have changed code.",
    )

    assert coerced is not None
    assert coerced["edits"] == []
    report = coerced["report"]
    assert report["status"] == "done"
    assert report["files_changed"] == []
    assert report["tests_run"] == ["pytest tests/test_math_utils.py -q"]
    assert "ignored a stray code-change claim" in report["summary"].lower()
    assert any("non-editing" in item.lower() for item in report["blockers"])


def test_coerce_non_editing_contract_violation_blocks_when_no_test_evidence() -> None:
    prompt = 'Editing expected for this task: no\n{"report": {}, "edits": []}'
    text = """
    {
      "report": {
        "agent": "Validation Specialist",
        "task_id": "1",
        "status": "done",
        "summary": "Updated src/math_utils.py while reproducing the failure.",
        "files_changed": ["src/math_utils.py"],
        "tests_run": [],
        "blockers": [],
        "risks": [],
        "recommended_next_task": "Implement the smallest safe code fix."
      },
      "edits": []
    }
    """

    coerced = ollama_adapter._coerce_non_editing_contract_violation(
        prompt,
        text,
        "This task was marked as non-editing, so do not claim to have changed code.",
    )

    assert coerced is not None
    report = coerced["report"]
    assert report["status"] == "blocked"
    assert report["files_changed"] == []
    assert "rejected a non-editing response" in report["summary"].lower()
    assert any("non-editing" in item.lower() for item in report["blockers"])


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


def test_main_coerces_non_editing_contract_violation_instead_of_failing(monkeypatch, capsys) -> None:
    calls: list[str] = []

    def fake_generate(model: str, prompt: str) -> str:
        calls.append(model)
        return json.dumps(
            {
                "report": {
                    "agent": "Validation Specialist",
                    "task_id": "1",
                    "status": "done",
                    "summary": "Updated src/math_utils.py while reproducing the failure.",
                    "files_changed": ["src/math_utils.py"],
                    "tests_run": ["pytest tests/test_math_utils.py -q"],
                    "blockers": ["Observed the target test failure."],
                    "risks": [],
                    "recommended_next_task": "Implement the smallest safe code fix.",
                },
                "edits": [],
            }
        )

    monkeypatch.setattr(ollama_adapter, "_candidate_models", lambda _requested: ["qwen2.5-coder:7b"])
    monkeypatch.setattr(ollama_adapter, "_generate", fake_generate)
    monkeypatch.setattr(
        ollama_adapter.sys,
        "stdin",
        io.StringIO('Editing expected for this task: no\n{"report": {}, "edits": []}'),
    )

    exit_code = ollama_adapter.main()
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    result = json.loads(payload["result"])

    assert exit_code == 0
    assert calls == ["qwen2.5-coder:7b", "qwen2.5-coder:7b", "qwen2.5-coder:7b", "qwen2.5-coder:7b"]
    assert result["report"]["status"] == "done"
    assert result["report"]["files_changed"] == []
    assert result["edits"] == []
