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
