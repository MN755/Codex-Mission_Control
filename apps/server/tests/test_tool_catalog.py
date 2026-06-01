from __future__ import annotations

from tool_catalog import catalog_with_permissions


def test_tool_catalog_surfaces_tensorflow_tools_when_repo_signals_exist(monkeypatch) -> None:
    monkeypatch.setattr(
        "tool_catalog.detect_tensorflow_repo_mode",
        lambda _root: {
            "enabled": True,
            "mode": "tensorflow_tfx",
            "frameworks": ["TensorFlow", "TensorBoard", "TFX", "SavedModel / Serving"],
            "product_workflows": ["notebook_experiments", "config_driven_runs"],
            "existing_savedmodel_artifacts": ["artifacts/exported_model/saved_model.pb"],
            "existing_tflite_artifacts": [],
        },
    )
    monkeypatch.setattr(
        "tool_catalog.build_tensorflow_validation_plan",
        lambda _root: {"summary": "TensorFlow validation planning is available."},
    )
    monkeypatch.setattr(
        "tool_catalog.shutil.which",
        lambda command: f"C:/tools/{command}.exe" if command in {"tensorboard", "saved_model_cli", "tfx", "jupyter", "python"} else None,
    )

    payload = catalog_with_permissions(provider="codex", connected_accounts={}, permission_overrides={})
    tools = {item["id"]: item for item in payload}

    assert tools["tensorflow-project-scaffolding"]["availability"] == "available"
    assert tools["tensorboard-observability"]["availability"] == "available"
    assert tools["tensorflow-serving-export"]["availability"] == "available"
    assert tools["tfx-pipeline-validation"]["availability"] == "available"
    assert tools["tensorflow-lite-export"]["availability"] == "experimental"
    assert tools["tensorflow-notebook-rescue"]["availability"] == "available"
    assert tools["ml-config-audit"]["availability"] == "available"


def test_tool_catalog_marks_tensorflow_tools_experimental_without_repo_signals(monkeypatch) -> None:
    monkeypatch.setattr(
        "tool_catalog.detect_tensorflow_repo_mode",
        lambda _root: {"enabled": False, "mode": None, "frameworks": [], "product_workflows": []},
    )
    monkeypatch.setattr(
        "tool_catalog.detect_pytorch_repo_mode",
        lambda _root: {"enabled": False, "mode": None, "frameworks": [], "product_workflows": [], "distributed_stack": [], "checkpoint_paths": [], "training_commands": [], "export_commands": [], "observability_commands": []},
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
    assert tools["tensorflow-notebook-rescue"]["availability"] == "experimental"
    assert tools["ml-config-audit"]["availability"] == "experimental"


def test_tool_catalog_allows_tensorboard_for_pytorch_observability(monkeypatch) -> None:
    monkeypatch.setattr(
        "tool_catalog.detect_tensorflow_repo_mode",
        lambda _root: {"enabled": False, "mode": None, "frameworks": []},
    )
    monkeypatch.setattr(
        "tool_catalog.detect_pytorch_repo_mode",
        lambda _root: {
            "enabled": True,
            "mode": "pytorch_general",
            "frameworks": ["PyTorch"],
            "product_workflows": ["training_observability"],
            "distributed_stack": [],
            "checkpoint_paths": [],
            "training_commands": ["python train.py"],
            "export_commands": [],
            "observability_commands": ["python -m tensorboard.main --logdir artifacts/tensorboard"],
        },
    )
    monkeypatch.setattr("tool_catalog.shutil.which", lambda command: "C:/tools/tensorboard.exe" if command == "tensorboard" else None)

    payload = catalog_with_permissions(provider="codex", connected_accounts={}, permission_overrides={})
    tools = {item["id"]: item for item in payload}

    assert tools["tensorboard-observability"]["availability"] == "available"


def test_tool_catalog_surfaces_pytorch_tools_when_repo_signals_exist(monkeypatch) -> None:
    monkeypatch.setattr(
        "tool_catalog.detect_pytorch_repo_mode",
        lambda _root: {
            "enabled": True,
            "mode": "pytorch_distributed",
            "frameworks": ["PyTorch", "TorchVision", "Accelerate", "Transformers / PEFT"],
            "product_workflows": ["distributed_training", "training_observability", "model_export", "notebook_experiments", "config_driven_runs"],
            "distributed_stack": ["Accelerate", "DDP/FSDP"],
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
        lambda _root: {"status": "ready", "summary": "PyTorch runtime is ready.", "cuda_available": True, "distributed_backends": ["nccl", "gloo"]},
    )
    monkeypatch.setattr(
        "tool_catalog.shutil.which",
        lambda command: f"C:/tools/{command}.exe" if command in {"tensorboard", "torchrun", "accelerate", "python", "jupyter"} else None,
    )

    payload = catalog_with_permissions(provider="codex", connected_accounts={}, permission_overrides={})
    tools = {item["id"]: item for item in payload}

    assert tools["pytorch-project-scaffolding"]["availability"] == "available"
    assert tools["pytorch-runtime-readiness"]["availability"] == "available"
    assert tools["pytorch-profiler-observability"]["availability"] == "available"
    assert tools["pytorch-checkpoint-validation"]["availability"] == "available"
    assert tools["pytorch-distributed-readiness"]["availability"] == "available"
    assert tools["pytorch-export-validation"]["availability"] == "available"
    assert tools["pytorch-notebook-rescue"]["availability"] == "available"
    assert tools["ml-config-audit"]["availability"] == "available"


def test_tool_catalog_marks_pytorch_tools_experimental_without_repo_signals(monkeypatch) -> None:
    monkeypatch.setattr(
        "tool_catalog.detect_pytorch_repo_mode",
        lambda _root: {"enabled": False, "mode": None, "frameworks": [], "product_workflows": [], "distributed_stack": [], "checkpoint_paths": [], "training_commands": [], "export_commands": [], "observability_commands": []},
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


def test_tool_catalog_treats_partial_pytorch_runtime_as_available(monkeypatch) -> None:
    monkeypatch.setattr(
        "tool_catalog.detect_pytorch_runtime_status",
        lambda _root: {"status": "partial", "summary": "CPU-only PyTorch runtime is still usable.", "distributed_backends": ["gloo"]},
    )

    payload = catalog_with_permissions(provider="codex", connected_accounts={}, permission_overrides={})
    tools = {item["id"]: item for item in payload}

    assert tools["pytorch-runtime-readiness"]["availability"] == "available"


def test_tool_catalog_allows_pytorch_observability_when_repo_has_commands_but_no_tensorboard(monkeypatch) -> None:
    monkeypatch.setattr(
        "tool_catalog.detect_pytorch_repo_mode",
        lambda _root: {
            "enabled": True,
            "mode": "pytorch_basic",
            "frameworks": ["PyTorch"],
            "product_workflows": ["training_observability"],
            "distributed_stack": [],
            "checkpoint_paths": [],
            "training_commands": ["python train.py"],
            "export_commands": [],
            "observability_commands": ["python -m torch.utils.bottleneck train.py"],
        },
    )
    monkeypatch.setattr("tool_catalog.shutil.which", lambda _command: None)

    payload = catalog_with_permissions(provider="codex", connected_accounts={}, permission_overrides={})
    tools = {item["id"]: item for item in payload}

    assert tools["pytorch-profiler-observability"]["availability"] == "available"


def test_tool_catalog_requires_specific_distributed_clis_for_signaled_stacks(monkeypatch) -> None:
    monkeypatch.setattr(
        "tool_catalog.detect_pytorch_repo_mode",
        lambda _root: {
            "enabled": True,
            "mode": "pytorch_distributed",
            "frameworks": ["PyTorch", "Accelerate"],
            "product_workflows": ["distributed_training"],
            "distributed_stack": ["Accelerate"],
            "checkpoint_paths": [],
            "training_commands": ["python train.py"],
            "export_commands": [],
            "observability_commands": [],
        },
    )
    monkeypatch.setattr(
        "tool_catalog.detect_pytorch_runtime_status",
        lambda _root: {"status": "ready", "summary": "CUDA is available.", "cuda_available": True, "distributed_backends": ["nccl", "gloo"]},
    )
    monkeypatch.setattr("tool_catalog.shutil.which", lambda command: None if command == "accelerate" else "C:/tools/python.exe")

    payload = catalog_with_permissions(provider="codex", connected_accounts={}, permission_overrides={})
    tools = {item["id"]: item for item in payload}

    assert tools["pytorch-distributed-readiness"]["availability"] == "needs_setup"


def test_tool_catalog_requires_torchrun_for_ddp_even_when_gloo_backend_exists(monkeypatch) -> None:
    monkeypatch.setattr(
        "tool_catalog.detect_pytorch_repo_mode",
        lambda _root: {
            "enabled": True,
            "mode": "pytorch_distributed",
            "frameworks": ["PyTorch"],
            "product_workflows": ["distributed_training"],
            "distributed_stack": ["DDP/FSDP"],
            "checkpoint_paths": [],
            "training_commands": ["torchrun --nproc_per_node 2 train.py"],
            "export_commands": [],
            "observability_commands": [],
        },
    )
    monkeypatch.setattr(
        "tool_catalog.detect_pytorch_runtime_status",
        lambda _root: {"status": "ready", "summary": "CPU runtime", "cuda_available": False, "distributed_backends": ["gloo"]},
    )
    monkeypatch.setattr("tool_catalog.shutil.which", lambda command: None if command == "torchrun" else "C:/tools/python.exe")

    payload = catalog_with_permissions(provider="codex", connected_accounts={}, permission_overrides={})
    tools = {item["id"]: item for item in payload}

    assert tools["pytorch-distributed-readiness"]["availability"] == "needs_setup"


def test_tool_catalog_caches_repo_detection_and_runtime_probes(monkeypatch) -> None:
    counters = {
        "tensorflow_mode": 0,
        "tensorflow_plan": 0,
        "pytorch_mode": 0,
        "pytorch_plan": 0,
        "pytorch_runtime": 0,
    }

    def fake_tensorflow_mode(_root):
        counters["tensorflow_mode"] += 1
        return {"enabled": True, "mode": "tensorflow_product", "frameworks": ["TensorFlow", "SavedModel / Serving"], "export_commands": ["python export.py"]}

    def fake_tensorflow_plan(_root):
        counters["tensorflow_plan"] += 1
        return {"summary": "TensorFlow validation planning is available."}

    def fake_pytorch_mode(_root):
        counters["pytorch_mode"] += 1
        return {
            "enabled": True,
            "mode": "pytorch_distributed",
            "frameworks": ["PyTorch"],
            "product_workflows": ["distributed_training", "training_observability", "model_export"],
            "distributed_stack": ["DDP/FSDP"],
            "checkpoint_paths": ["checkpoints/model.pt"],
            "training_commands": ["python train.py"],
            "export_commands": ["python export.py"],
            "observability_commands": ["python -m torch.utils.bottleneck train.py"],
        }

    def fake_pytorch_plan(_root):
        counters["pytorch_plan"] += 1
        return {"summary": "PyTorch validation planning is available."}

    def fake_pytorch_runtime(_root):
        counters["pytorch_runtime"] += 1
        return {"status": "ready", "summary": "PyTorch runtime is ready.", "cuda_available": True, "distributed_backends": ["nccl", "gloo"]}

    monkeypatch.setattr("tool_catalog.detect_tensorflow_repo_mode", fake_tensorflow_mode)
    monkeypatch.setattr("tool_catalog.build_tensorflow_validation_plan", fake_tensorflow_plan)
    monkeypatch.setattr("tool_catalog.detect_pytorch_repo_mode", fake_pytorch_mode)
    monkeypatch.setattr("tool_catalog.build_pytorch_validation_plan", fake_pytorch_plan)
    monkeypatch.setattr("tool_catalog.detect_pytorch_runtime_status", fake_pytorch_runtime)
    monkeypatch.setattr("tool_catalog.shutil.which", lambda _command: None)

    payload = catalog_with_permissions(provider="codex", connected_accounts={}, permission_overrides={})

    assert payload
    assert counters["tensorflow_mode"] == 1
    assert counters["tensorflow_plan"] == 1
    assert counters["pytorch_mode"] == 1
    assert counters["pytorch_plan"] == 1
    assert counters["pytorch_runtime"] == 1


def test_tool_catalog_accepts_repo_native_tensorflow_export_commands_without_clis(monkeypatch) -> None:
    monkeypatch.setattr(
        "tool_catalog.detect_tensorflow_repo_mode",
        lambda _root: {
            "enabled": True,
            "mode": "tensorflow_product",
            "frameworks": ["TensorFlow", "SavedModel / Serving", "TensorFlow Lite"],
            "export_commands": ["python export.py"],
        },
    )
    monkeypatch.setattr("tool_catalog.shutil.which", lambda _command: None)

    payload = catalog_with_permissions(provider="codex", connected_accounts={}, permission_overrides={})
    tools = {item["id"]: item for item in payload}

    assert tools["tensorflow-serving-export"]["availability"] == "available"
    assert tools["tensorflow-lite-export"]["availability"] == "available"


def test_tool_catalog_accepts_tensorflow_artifacts_without_repo_export_commands(monkeypatch) -> None:
    monkeypatch.setattr(
        "tool_catalog.detect_tensorflow_repo_mode",
        lambda _root: {
            "enabled": True,
            "mode": "tensorflow_product",
            "frameworks": ["TensorFlow", "SavedModel / Serving", "TensorFlow Lite"],
            "product_workflows": [],
            "export_commands": [],
            "existing_savedmodel_artifacts": ["artifacts/exported_model/saved_model.pb"],
            "existing_tflite_artifacts": ["artifacts/model.tflite"],
        },
    )
    monkeypatch.setattr("tool_catalog.shutil.which", lambda _command: None)

    payload = catalog_with_permissions(provider="codex", connected_accounts={}, permission_overrides={})
    tools = {item["id"]: item for item in payload}

    assert tools["tensorflow-serving-export"]["availability"] == "available"
    assert tools["tensorflow-lite-export"]["availability"] == "available"


def test_tool_catalog_requires_jupyter_for_notebook_rescue(monkeypatch) -> None:
    monkeypatch.setattr(
        "tool_catalog.detect_tensorflow_repo_mode",
        lambda _root: {
            "enabled": True,
            "mode": "tensorflow_product",
            "frameworks": ["TensorFlow"],
            "product_workflows": ["notebook_experiments"],
        },
    )
    monkeypatch.setattr("tool_catalog.shutil.which", lambda command: "C:/tools/python.exe" if command == "python" else None)

    payload = catalog_with_permissions(provider="codex", connected_accounts={}, permission_overrides={})
    tools = {item["id"]: item for item in payload}

    assert tools["tensorflow-notebook-rescue"]["availability"] == "needs_setup"


def test_tool_catalog_requires_python_for_ml_config_audit(monkeypatch) -> None:
    monkeypatch.setattr(
        "tool_catalog.detect_tensorflow_repo_mode",
        lambda _root: {"enabled": False, "mode": None, "frameworks": [], "product_workflows": []},
    )
    monkeypatch.setattr(
        "tool_catalog.detect_pytorch_repo_mode",
        lambda _root: {
            "enabled": True,
            "mode": "pytorch_general",
            "frameworks": ["PyTorch"],
            "product_workflows": ["config_driven_runs"],
            "distributed_stack": [],
            "checkpoint_paths": [],
            "training_commands": ["python train.py"],
            "export_commands": [],
            "observability_commands": [],
        },
    )
    monkeypatch.setattr("tool_catalog.shutil.which", lambda command: "C:/tools/jupyter.exe" if command == "jupyter" else None)

    payload = catalog_with_permissions(provider="codex", connected_accounts={}, permission_overrides={})
    tools = {item["id"]: item for item in payload}

    assert tools["ml-config-audit"]["availability"] == "needs_setup"
