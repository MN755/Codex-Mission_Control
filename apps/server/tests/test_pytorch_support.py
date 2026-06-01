from __future__ import annotations

import json
from pathlib import Path

from conftest import sample_workspace
from pytorch_support import (
    build_pytorch_validation_plan,
    detect_pytorch_repo_mode,
    detect_pytorch_runtime_status,
)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_detect_pytorch_repo_mode_finds_training_export_and_distributed_signals() -> None:
    workspace = Path(sample_workspace("pytorch-detect"))
    workspace.mkdir(parents=True, exist_ok=True)
    _write(
        workspace / "pyproject.toml",
        """
        [project]
        name = "torch-demo"
        dependencies = [
          "torch>=2.6",
          "torchvision",
          "accelerate",
          "transformers",
          "peft"
        ]
        """,
    )
    _write(workspace / "train.py", "import torch\n")
    _write(workspace / "export.py", "import torch\n")
    _write(workspace / "checkpoints" / "model.ckpt", "binary-ish\n")

    payload = detect_pytorch_repo_mode(workspace)

    assert payload["enabled"] is True
    assert payload["mode"] == "pytorch_distributed"
    assert "PyTorch" in payload["frameworks"]
    assert "TorchVision" in payload["frameworks"]
    assert "Accelerate" in payload["frameworks"]
    assert "Transformers / PEFT" in payload["frameworks"]
    assert "python -m pip install -e ." in payload["build_commands"]
    assert "python train.py" in payload["training_commands"]
    assert "python export.py" in payload["export_commands"]
    assert "distributed_training" in payload["product_workflows"]
    assert any(path.endswith(".ckpt") for path in payload["checkpoint_paths"])


def test_detect_pytorch_repo_mode_does_not_treat_marketing_readme_as_repo_signal(tmp_path: Path) -> None:
    workspace = tmp_path / "pytorch-readme-only"
    workspace.mkdir(parents=True, exist_ok=True)
    _write(workspace / "README.md", "Mission Control can help with PyTorch, Lightning, Accelerate, and ONNX.\n")

    payload = detect_pytorch_repo_mode(workspace)

    assert payload["enabled"] is False
    assert payload["mode"] is None


def test_detect_pytorch_runtime_status_handles_missing_torch_gracefully(monkeypatch) -> None:
    workspace = Path(sample_workspace("pytorch-runtime-missing"))
    workspace.mkdir(parents=True, exist_ok=True)
    _write(workspace / "requirements.txt", "torch\n")
    _write(workspace / "train.py", "print('train')\n")

    class _Completed:
        def __init__(self, stdout: str) -> None:
            self.stdout = stdout

    monkeypatch.setattr(
        "pytorch_support.subprocess.run",
        lambda *args, **kwargs: _Completed(json.dumps({"ok": False, "error": "No module named 'torch'"})),
    )
    monkeypatch.setattr("pytorch_support.shutil.which", lambda _command: None)

    payload = detect_pytorch_runtime_status(workspace)

    assert payload["available"] is False
    assert payload["status"] == "blocked"
    assert payload["torch_installed"] is False
    assert "No module named 'torch'" in payload["blockers"][0]


def test_detect_pytorch_runtime_status_tolerates_noise_before_json_payload(monkeypatch) -> None:
    workspace = Path(sample_workspace("pytorch-runtime-noisy-stdout"))
    workspace.mkdir(parents=True, exist_ok=True)
    _write(workspace / "requirements.txt", "torch\n")
    _write(workspace / "train.py", "print('train')\n")

    class _Completed:
        def __init__(self, stdout: str) -> None:
            self.stdout = stdout

    monkeypatch.setattr(
        "pytorch_support.subprocess.run",
        lambda *args, **kwargs: _Completed("warning: startup noise\n{\"ok\": true, \"torch_version\": \"2.7.0\", \"cuda_available\": false, \"mps_available\": true, \"device_count\": 0, \"cuda_version\": null, \"cudnn_available\": false}\n"),
    )
    monkeypatch.setattr("pytorch_support.shutil.which", lambda _command: "C:/tools/python.exe")

    payload = detect_pytorch_runtime_status(workspace)

    assert payload["available"] is True
    assert payload["status"] == "ready"
    assert payload["torch_version"] == "2.7.0"
    assert payload["mps_available"] is True


def test_pytorch_validation_plan_surfaces_training_export_checkpoint_and_runtime_steps(monkeypatch) -> None:
    workspace = Path(sample_workspace("pytorch-plan"))
    workspace.mkdir(parents=True, exist_ok=True)
    _write(
        workspace / "requirements.txt",
        """
        torch
        torchvision
        accelerate
        onnx
        pytest
        """,
    )
    _write(workspace / "train.py", "print('train')\n")
    _write(workspace / "eval.py", "print('eval')\n")
    _write(workspace / "infer.py", "print('infer')\n")
    _write(workspace / "export.py", "print('export')\n")
    _write(workspace / "checkpoints" / "model.pt", "weights\n")

    monkeypatch.setattr(
        "pytorch_support.detect_pytorch_runtime_status",
        lambda _workspace: {
            "available": True,
            "status": "ready",
            "summary": "PyTorch runtime is ready.",
            "torch_installed": True,
            "cuda_available": True,
            "mps_available": False,
            "device_count": 1,
            "torch_version": "2.7.0",
            "cuda_version": "12.4",
            "cudnn_available": True,
            "distributed_backends": ["nccl", "gloo"],
            "blockers": [],
            "recommended_fixes": [],
        },
    )

    payload = build_pytorch_validation_plan(workspace)

    assert payload["available"] is True
    assert payload["status"] == "ready"
    assert any(step["type"] == "train" for step in payload["steps"])
    assert any(step["type"] == "eval" for step in payload["steps"])
    assert any(step["type"] == "inference" for step in payload["steps"])
    assert any(step["type"] == "export" for step in payload["steps"])
    assert any(step["type"] == "checkpoint" for step in payload["steps"])
    assert any(step["type"] == "sanity" and "wire repo-specific" not in step["command"] for step in payload["steps"])
    assert any(step["type"] == "checkpoint" and "torch.load" in step["command"] for step in payload["steps"])
    assert any("device, precision, and batch-size" in target.lower() for target in payload["evidence_targets"])


def test_pytorch_validation_plan_keeps_partial_runtime_status(monkeypatch) -> None:
    workspace = Path(sample_workspace("pytorch-plan-partial-runtime"))
    workspace.mkdir(parents=True, exist_ok=True)
    _write(workspace / "requirements.txt", "torch\npytest\n")
    _write(workspace / "train.py", "print('train')\n")

    monkeypatch.setattr(
        "pytorch_support.detect_pytorch_runtime_status",
        lambda _workspace: {
            "available": True,
            "status": "partial",
            "summary": "CPU only",
            "torch_installed": True,
            "cuda_available": False,
            "mps_available": False,
            "device_count": 0,
            "torch_version": "2.7.0",
            "cuda_version": None,
            "cudnn_available": False,
            "distributed_backends": ["gloo"],
            "blockers": [],
            "recommended_fixes": [],
        },
    )

    payload = build_pytorch_validation_plan(workspace)

    assert payload["status"] == "partial"
    assert payload["runtime_status"] == "partial"


def test_detect_pytorch_repo_mode_ignores_artifact_flood_and_finds_real_repo_signals(tmp_path: Path) -> None:
    workspace = tmp_path / "artifact-heavy-pytorch"
    (workspace / "artifacts").mkdir(parents=True, exist_ok=True)
    for index in range(1800):
        _write(workspace / "artifacts" / f"noise-{index}.txt", "x\n")
    _write(workspace / "pyproject.toml", "[project]\ndependencies=['torch','accelerate']\n")
    _write(workspace / "train.py", "import torch\n")

    payload = detect_pytorch_repo_mode(workspace)

    assert payload["enabled"] is True
    assert "python train.py" in payload["training_commands"]


def test_detect_pytorch_repo_mode_prioritizes_real_entrypoints_in_large_repo(tmp_path: Path) -> None:
    workspace = tmp_path / "pytorch-priority-signals"
    workspace.mkdir(parents=True, exist_ok=True)
    _write(workspace / "pyproject.toml", "[project]\ndependencies=['torch','accelerate']\n")
    for index in range(40):
        _write(workspace / f"module_{index:02d}.py", "print('noise')\n")
    _write(workspace / "train.py", "import torch\nimport accelerate\n")

    payload = detect_pytorch_repo_mode(workspace)

    assert payload["enabled"] is True
    assert "Accelerate" in payload["frameworks"]
    assert "python train.py" in payload["training_commands"]
    assert "accelerate launch train.py" in payload["training_commands"]


def test_detect_pytorch_repo_mode_discovers_nested_entrypoints_and_observability_dirs(tmp_path: Path) -> None:
    workspace = tmp_path / "pytorch-nested-entrypoints"
    workspace.mkdir(parents=True, exist_ok=True)
    _write(workspace / "apps" / "trainer" / "pyproject.toml", "[project]\ndependencies=['torch','accelerate','wandb','mlflow']\n")
    _write(workspace / "apps" / "trainer" / "train.py", "import torch\nimport accelerate\nimport wandb\nimport mlflow\n")
    _write(workspace / "apps" / "trainer" / "eval.py", "print('eval')\n")
    _write(workspace / "apps" / "trainer" / "infer.py", "print('infer')\n")
    _write(workspace / "apps" / "trainer" / "export.py", "torch.onnx.export\n")
    _write(workspace / "apps" / "trainer" / "wandb" / "latest-run.txt", "run\n")
    _write(workspace / "apps" / "trainer" / "mlruns" / "meta.yaml", "run: 1\n")

    payload = detect_pytorch_repo_mode(workspace)

    assert "python -m pip install -e apps/trainer" in payload["build_commands"]
    assert "python apps/trainer/train.py" in payload["training_commands"]
    assert "accelerate launch apps/trainer/train.py" in payload["training_commands"]
    assert "python apps/trainer/eval.py" in payload["evaluation_commands"]
    assert "python apps/trainer/infer.py" in payload["inference_commands"]
    assert "python apps/trainer/export.py" in payload["export_commands"]
    assert "wandb sync apps/trainer/wandb" in payload["observability_commands"]
    assert "mlflow ui --backend-store-uri apps/trainer/mlruns" in payload["observability_commands"]


def test_detect_pytorch_repo_mode_uses_real_nested_tensorboard_logdir(tmp_path: Path) -> None:
    workspace = tmp_path / "pytorch-nested-logs"
    workspace.mkdir(parents=True, exist_ok=True)
    _write(workspace / "pyproject.toml", "[project]\ndependencies=['torch','tensorboard']\n")
    _write(workspace / "train.py", "import torch\nwith torch.profiler.profile():\n    pass\n")
    (workspace / "services" / "trainer" / "artifacts" / "tensorboard").mkdir(parents=True, exist_ok=True)

    payload = detect_pytorch_repo_mode(workspace)

    assert "python -m tensorboard.main --logdir services/trainer/artifacts/tensorboard" in payload["observability_commands"]


def test_detect_pytorch_repo_mode_ignores_readme_hype_for_advanced_frameworks(tmp_path: Path) -> None:
    workspace = tmp_path / "pytorch-readme-hype"
    workspace.mkdir(parents=True, exist_ok=True)
    _write(workspace / "pyproject.toml", "[project]\ndependencies=['torch']\n")
    _write(workspace / "train.py", "import torch\n")
    _write(workspace / "README.md", "This repo totally uses Accelerate, DeepSpeed, TorchScript, ONNX, and LoRA.\n")

    payload = detect_pytorch_repo_mode(workspace)

    assert payload["enabled"] is True
    assert "Accelerate" not in payload["frameworks"]
    assert "DeepSpeed" not in payload["frameworks"]
    assert "distributed_training" not in payload["product_workflows"]
    assert "model_export" not in payload["product_workflows"]
    assert "llm_finetuning" not in payload["product_workflows"]


def test_detect_pytorch_repo_mode_uses_repo_specific_distributed_launchers(tmp_path: Path) -> None:
    accelerate_workspace = tmp_path / "pytorch-accelerate"
    accelerate_workspace.mkdir(parents=True, exist_ok=True)
    _write(accelerate_workspace / "pyproject.toml", "[project]\ndependencies=['torch','accelerate']\n")
    _write(accelerate_workspace / "train.py", "import accelerate\n")

    accelerate_payload = detect_pytorch_repo_mode(accelerate_workspace)

    assert "accelerate launch train.py" in accelerate_payload["training_commands"]
    assert not any(command.startswith("torchrun ") for command in accelerate_payload["training_commands"])

    deepspeed_workspace = tmp_path / "pytorch-deepspeed"
    deepspeed_workspace.mkdir(parents=True, exist_ok=True)
    _write(deepspeed_workspace / "pyproject.toml", "[project]\ndependencies=['torch','deepspeed']\n")
    _write(deepspeed_workspace / "train.py", "import deepspeed\n")

    deepspeed_payload = detect_pytorch_repo_mode(deepspeed_workspace)

    assert "deepspeed train.py --deepspeed ds_config.json" in deepspeed_payload["training_commands"]

    hybrid_workspace = tmp_path / "pytorch-hybrid-launchers"
    hybrid_workspace.mkdir(parents=True, exist_ok=True)
    _write(hybrid_workspace / "pyproject.toml", "[project]\ndependencies=['torch','accelerate','deepspeed']\n")
    _write(hybrid_workspace / "train.py", "import accelerate\nimport deepspeed\n")

    hybrid_payload = detect_pytorch_repo_mode(hybrid_workspace)

    assert "accelerate launch train.py" in hybrid_payload["training_commands"]
    assert "deepspeed train.py --deepspeed ds_config.json" in hybrid_payload["training_commands"]


def test_detect_pytorch_repo_mode_does_not_invent_fake_export_command(tmp_path: Path) -> None:
    workspace = tmp_path / "pytorch-no-export-entry"
    workspace.mkdir(parents=True, exist_ok=True)
    _write(workspace / "pyproject.toml", "[project]\ndependencies=['torch','onnx']\n")
    _write(workspace / "train.py", "import torch\n")
    _write(workspace / "notes.py", "torch.onnx.export\n")

    payload = detect_pytorch_repo_mode(workspace)

    assert payload["enabled"] is True
    assert payload["export_commands"] == []


def test_pytorch_validation_plan_does_not_warn_cpu_only_for_accelerate_only_repo(monkeypatch) -> None:
    workspace = Path(sample_workspace("pytorch-plan-accelerate-cpu"))
    workspace.mkdir(parents=True, exist_ok=True)
    _write(workspace / "requirements.txt", "torch\naccelerate\npytest\n")
    _write(workspace / "train.py", "print('train')\n")

    monkeypatch.setattr(
        "pytorch_support.detect_pytorch_runtime_status",
        lambda _workspace: {
            "available": True,
            "status": "partial",
            "summary": "CPU only",
            "torch_installed": True,
            "cuda_available": False,
            "mps_available": False,
            "device_count": 0,
            "torch_version": "2.7.0",
            "cuda_version": None,
            "cudnn_available": False,
            "distributed_backends": ["gloo"],
            "blockers": [],
            "recommended_fixes": [],
        },
    )

    payload = build_pytorch_validation_plan(workspace)

    assert not any("cpu-only" in item.lower() for item in payload["recommended_fixes"])


def test_detect_pytorch_runtime_status_recommends_stack_specific_clis(monkeypatch) -> None:
    workspace = Path(sample_workspace("pytorch-runtime-stack-specific"))
    workspace.mkdir(parents=True, exist_ok=True)
    _write(workspace / "pyproject.toml", "[project]\ndependencies=['torch','accelerate','deepspeed']\n")
    _write(workspace / "train.py", "import accelerate\nimport deepspeed\n")

    class _Completed:
        def __init__(self, stdout: str) -> None:
            self.stdout = stdout

    monkeypatch.setattr(
        "pytorch_support.subprocess.run",
        lambda *args, **kwargs: _Completed(json.dumps({"ok": True, "torch_version": "2.7.0", "cuda_available": False, "mps_available": False, "device_count": 0, "cuda_version": None, "cudnn_available": False})),
    )
    monkeypatch.setattr("pytorch_support.shutil.which", lambda command: None if command in {"accelerate", "deepspeed", "nvidia-smi"} else "C:/tools/python.exe")

    payload = detect_pytorch_runtime_status(workspace)

    fixes = " ".join(payload["recommended_fixes"])
    assert "Accelerate CLI" in fixes
    assert "DeepSpeed CLI" in fixes
    assert "expect CUDA" in fixes


def test_detect_pytorch_runtime_status_recommends_torchrun_for_ddp(monkeypatch) -> None:
    workspace = Path(sample_workspace("pytorch-runtime-ddp-cli"))
    workspace.mkdir(parents=True, exist_ok=True)
    _write(workspace / "pyproject.toml", "[project]\ndependencies=['torch']\n")
    _write(workspace / "train.py", "import torch.distributed\n")

    class _Completed:
        def __init__(self, stdout: str) -> None:
            self.stdout = stdout

    monkeypatch.setattr(
        "pytorch_support.subprocess.run",
        lambda *args, **kwargs: _Completed(json.dumps({"ok": True, "torch_version": "2.7.0", "cuda_available": True, "mps_available": False, "device_count": 1, "cuda_version": "12.4", "cudnn_available": True})),
    )
    monkeypatch.setattr("pytorch_support.shutil.which", lambda command: None if command in {"torchrun"} else "C:/tools/python.exe")

    payload = detect_pytorch_runtime_status(workspace)

    assert any("torchrun" in fix for fix in payload["recommended_fixes"])


def test_detect_pytorch_runtime_status_blocks_inconsistent_cuda_visibility(monkeypatch) -> None:
    workspace = Path(sample_workspace("pytorch-runtime-inconsistent-cuda"))
    workspace.mkdir(parents=True, exist_ok=True)
    _write(workspace / "requirements.txt", "torch\n")
    _write(workspace / "train.py", "print('train')\n")

    class _Completed:
        def __init__(self, stdout: str) -> None:
            self.stdout = stdout

    monkeypatch.setattr(
        "pytorch_support.subprocess.run",
        lambda *args, **kwargs: _Completed(json.dumps({"ok": True, "torch_version": "2.7.0", "cuda_available": True, "mps_available": False, "device_count": 0, "cuda_version": "12.4", "cudnn_available": True})),
    )
    monkeypatch.setattr("pytorch_support.shutil.which", lambda _command: "C:/tools/python.exe")

    payload = detect_pytorch_runtime_status(workspace)

    assert payload["status"] == "blocked"
    assert any("no visible CUDA devices" in blocker for blocker in payload["blockers"])


def test_pytorch_validation_plan_escapes_checkpoint_path(monkeypatch, tmp_path: Path) -> None:
    workspace = tmp_path / "pytorch-quoted-checkpoint"
    workspace.mkdir(parents=True, exist_ok=True)
    _write(workspace / "requirements.txt", "torch\npytest\n")
    _write(workspace / "train.py", "print('train')\n")
    checkpoint_path = workspace / "checkpoints" / "model's-best.pt"
    _write(checkpoint_path, "weights\n")

    monkeypatch.setattr(
        "pytorch_support.detect_pytorch_runtime_status",
        lambda _workspace: {
            "available": True,
            "status": "ready",
            "summary": "ready",
            "torch_installed": True,
            "cuda_available": False,
            "mps_available": True,
            "device_count": 0,
            "torch_version": "2.7.0",
            "cuda_version": None,
            "cudnn_available": False,
            "distributed_backends": ["gloo"],
            "blockers": [],
            "recommended_fixes": [],
        },
    )

    payload = build_pytorch_validation_plan(workspace)

    checkpoint_step = next(step for step in payload["steps"] if step["type"] == "checkpoint")
    assert "model's-best.pt" in checkpoint_step["command"]
    assert 'torch.load("' in checkpoint_step["command"]


def test_pytorch_validation_plan_allows_export_only_repo(monkeypatch, tmp_path: Path) -> None:
    workspace = tmp_path / "pytorch-export-only"
    workspace.mkdir(parents=True, exist_ok=True)
    _write(workspace / "requirements.txt", "torch\nonnx\n")
    _write(workspace / "export.py", "import torch\n")
    _write(workspace / "notes.py", "torch.onnx.export\n")

    monkeypatch.setattr(
        "pytorch_support.detect_pytorch_runtime_status",
        lambda _workspace: {
            "available": True,
            "status": "partial",
            "summary": "CPU only",
            "torch_installed": True,
            "cuda_available": False,
            "mps_available": False,
            "device_count": 0,
            "torch_version": "2.7.0",
            "cuda_version": None,
            "cudnn_available": False,
            "distributed_backends": ["gloo"],
            "blockers": [],
            "recommended_fixes": [],
        },
    )

    payload = build_pytorch_validation_plan(workspace)

    assert payload["status"] == "partial"
    assert payload["blockers"] == []
    assert any(step["type"] == "export" and step["command"] == "python export.py" for step in payload["steps"])


def test_detect_pytorch_repo_mode_tailors_observability_commands_to_real_signals(tmp_path: Path) -> None:
    workspace = tmp_path / "pytorch-observability"
    (workspace / "artifacts" / "tensorboard").mkdir(parents=True, exist_ok=True)
    (workspace / "mlruns").mkdir(parents=True, exist_ok=True)
    (workspace / "wandb").mkdir(parents=True, exist_ok=True)
    _write(workspace / "pyproject.toml", "[project]\ndependencies=['torch','wandb','mlflow']\n")
    _write(
        workspace / "train.py",
        "import torch\nimport wandb\nimport mlflow\nwith torch.profiler.profile():\n    pass\n",
    )

    payload = detect_pytorch_repo_mode(workspace)

    assert "python -m torch.utils.bottleneck train.py" in payload["observability_commands"]
    assert "python -m tensorboard.main --logdir artifacts/tensorboard" in payload["observability_commands"]
    assert "wandb sync wandb" in payload["observability_commands"]
    assert "mlflow ui --backend-store-uri mlruns" in payload["observability_commands"]
    assert not any("<train_script>" in command for command in payload["observability_commands"])
