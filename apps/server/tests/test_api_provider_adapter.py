from __future__ import annotations

import importlib.util
from pathlib import Path


ADAPTER_PATH = Path(__file__).resolve().parents[3] / "scripts" / "api_provider_adapter.py"
SPEC = importlib.util.spec_from_file_location("mission_control_api_provider_adapter", ADAPTER_PATH)
assert SPEC is not None and SPEC.loader is not None
api_provider_adapter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(api_provider_adapter)


def test_endpoint_normalization_for_anthropic_and_openai(monkeypatch) -> None:
    monkeypatch.setenv("MISSION_CONTROL_PROVIDER", "anthropic_api")
    monkeypatch.setenv("MISSION_CONTROL_PROVIDER_ENDPOINT", "https://example.test/v1")
    assert api_provider_adapter._endpoint() == "https://example.test/v1/messages"

    monkeypatch.setenv("MISSION_CONTROL_PROVIDER", "openai_api")
    monkeypatch.setenv("MISSION_CONTROL_PROVIDER_ENDPOINT", "https://example.test")
    assert api_provider_adapter._endpoint() == "https://example.test/v1/chat/completions"


def test_model_defaults_follow_provider(monkeypatch) -> None:
    monkeypatch.delenv("MISSION_CONTROL_MODEL", raising=False)
    monkeypatch.setenv("MISSION_CONTROL_PROVIDER", "openai_api")
    assert api_provider_adapter._model() == "gpt-4o-mini"
    monkeypatch.setenv("MISSION_CONTROL_PROVIDER", "anthropic_api")
    assert api_provider_adapter._model() == "claude-3-5-sonnet-latest"
    monkeypatch.setenv("MISSION_CONTROL_PROVIDER", "nvidia_dynamo")
    assert api_provider_adapter._model() == "Qwen/Qwen3-0.6B"


def test_dynamo_endpoint_and_api_key_are_optional(monkeypatch) -> None:
    monkeypatch.setenv("MISSION_CONTROL_PROVIDER", "nvidia_dynamo")
    monkeypatch.setenv("MISSION_CONTROL_PROVIDER_ENDPOINT", "http://dynamo.local:8000")
    monkeypatch.delenv("NVIDIA_DYNAMO_API_KEY", raising=False)
    monkeypatch.delenv("MISSION_CONTROL_NVIDIA_DYNAMO_API_KEY", raising=False)

    assert api_provider_adapter._endpoint() == "http://dynamo.local:8000/v1/chat/completions"
    key_name, key_value = api_provider_adapter._api_key()
    assert key_name == "NVIDIA_DYNAMO_API_KEY"
    assert key_value == ""


def test_repair_reason_requires_json_for_edit_contract() -> None:
    prompt = 'Return only valid JSON matching this schema exactly: {"report": {}, "edits": []}'
    assert api_provider_adapter._repair_reason(prompt, "not json") is not None
    assert api_provider_adapter._repair_reason(prompt, '{"report": {}, "edits": []}') is None
