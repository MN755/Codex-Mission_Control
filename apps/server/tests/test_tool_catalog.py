from __future__ import annotations

from tool_catalog import catalog_with_permissions


def test_tool_catalog_surfaces_tensorflow_tools_when_repo_signals_exist(monkeypatch) -> None:
    monkeypatch.setattr(
        "tool_catalog.detect_tensorflow_repo_mode",
        lambda _root: {
            "enabled": True,
            "mode": "tensorflow_tfx",
            "frameworks": ["TensorFlow", "TensorBoard", "TFX", "SavedModel / Serving"],
        },
    )
    monkeypatch.setattr(
        "tool_catalog.build_tensorflow_validation_plan",
        lambda _root: {"summary": "TensorFlow validation planning is available."},
    )
    monkeypatch.setattr(
        "tool_catalog.shutil.which",
        lambda command: f"C:/tools/{command}.exe" if command in {"tensorboard", "saved_model_cli", "tfx"} else None,
    )

    payload = catalog_with_permissions(provider="codex", connected_accounts={}, permission_overrides={})
    tools = {item["id"]: item for item in payload}

    assert tools["tensorflow-project-scaffolding"]["availability"] == "available"
    assert tools["tensorboard-observability"]["availability"] == "available"
    assert tools["tensorflow-serving-export"]["availability"] == "available"
    assert tools["tfx-pipeline-validation"]["availability"] == "available"
    assert tools["tensorflow-lite-export"]["availability"] == "experimental"


def test_tool_catalog_marks_tensorflow_tools_experimental_without_repo_signals(monkeypatch) -> None:
    monkeypatch.setattr(
        "tool_catalog.detect_tensorflow_repo_mode",
        lambda _root: {"enabled": False, "mode": None, "frameworks": []},
    )
    monkeypatch.setattr(
        "tool_catalog.build_tensorflow_validation_plan",
        lambda _root: {"summary": "TensorFlow validation planning is not applicable."},
    )
    monkeypatch.setattr("tool_catalog.shutil.which", lambda _command: None)

    payload = catalog_with_permissions(provider="codex", connected_accounts={}, permission_overrides={})
    tools = {item["id"]: item for item in payload}

    assert tools["tensorflow-project-scaffolding"]["availability"] == "needs_setup"
    assert tools["tensorboard-observability"]["availability"] == "experimental"
    assert tools["tfx-pipeline-validation"]["availability"] == "experimental"


def test_tool_catalog_surfaces_pytorch_tools_when_repo_signals_exist(monkeypatch) -> None:
    monkeypatch.setattr(
        "tool_catalog.detect_pytorch_repo_mode",
        lambda _root: {
            "enabled": True,
            "mode": "pytorch_distributed",
            "frameworks": ["PyTorch", "TorchVision", "Accelerate", "Transformers / PEFT"],
            "product_workflows": ["distributed_training", "training_observability", "model_export"],
            "checkpoint_paths": ["checkpoints/model.pt"],
            "training_commands": ["python train.py"],
            "export_commands": ["python export.py"],
            "observability_commands": ["python -m torch.utils.bottleneck train.py"],
        },
    )
    monkeypatch.setattr(
        "tool_catalog.build_pytorch_validation_plan",
        lambda _root: {"summary": "PyTorch validation planning is available."},
    )
    monkeypatch.setattr(
        "tool_catalog.detect_pytorch_runtime_status",
        lambda _root: {"status": "ready", "summary": "PyTorch runtime is ready.", "cuda_available": True},
    )
    monkeypatch.setattr(
        "tool_catalog.shutil.which",
        lambda command: f"C:/tools/{command}.exe" if command in {"tensorboard", "torchrun", "python"} else None,
    )

    payload = catalog_with_permissions(provider="codex", connected_accounts={}, permission_overrides={})
    tools = {item["id"]: item for item in payload}

    assert tools["pytorch-project-scaffolding"]["availability"] == "available"
    assert tools["pytorch-runtime-readiness"]["availability"] == "available"
    assert tools["pytorch-profiler-observability"]["availability"] == "available"
    assert tools["pytorch-checkpoint-validation"]["availability"] == "available"
    assert tools["pytorch-distributed-readiness"]["availability"] == "available"
    assert tools["pytorch-export-validation"]["availability"] == "available"


def test_tool_catalog_marks_pytorch_tools_experimental_without_repo_signals(monkeypatch) -> None:
    monkeypatch.setattr(
        "tool_catalog.detect_pytorch_repo_mode",
        lambda _root: {"enabled": False, "mode": None, "frameworks": [], "product_workflows": [], "checkpoint_paths": [], "training_commands": [], "export_commands": [], "observability_commands": []},
    )
    monkeypatch.setattr(
        "tool_catalog.build_pytorch_validation_plan",
        lambda _root: {"summary": "PyTorch validation planning is not applicable."},
    )
    monkeypatch.setattr(
        "tool_catalog.detect_pytorch_runtime_status",
        lambda _root: {"status": "not_applicable", "summary": "This workspace does not currently look like a PyTorch repo."},
    )
    monkeypatch.setattr("tool_catalog.shutil.which", lambda _command: None)

    payload = catalog_with_permissions(provider="codex", connected_accounts={}, permission_overrides={})
    tools = {item["id"]: item for item in payload}

    assert tools["pytorch-project-scaffolding"]["availability"] == "needs_setup"
    assert tools["pytorch-runtime-readiness"]["availability"] == "experimental"
    assert tools["pytorch-profiler-observability"]["availability"] == "experimental"
    assert tools["pytorch-distributed-readiness"]["availability"] == "experimental"
    assert tools["pytorch-export-validation"]["availability"] == "experimental"
