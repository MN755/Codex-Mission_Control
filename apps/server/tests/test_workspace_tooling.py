from __future__ import annotations

import json
import subprocess
from pathlib import Path

from manager import service
from models import Project
from workspace_tooling import detect_workspace_tooling


def test_detect_workspace_tooling_summarizes_repo_native_helpers(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname='demo'\n[tool.ruff]\nline-length = 100\n",
        encoding="utf-8",
    )
    (tmp_path / "uv.lock").write_text("version = 1\n", encoding="utf-8")
    (tmp_path / ".pre-commit-config.yaml").write_text("repos: []\n", encoding="utf-8")
    (tmp_path / "noxfile.py").write_text("import nox\n", encoding="utf-8")
    (tmp_path / "package.json").write_text(
        json.dumps({"devDependencies": {"@playwright/test": "^1.55.0"}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "workspace_tooling._which",
        lambda command: f"C:/tools/{command}.exe" if command in {"uv", "ruff", "pre-commit", "rg", "gitleaks"} else None,
    )

    payload = detect_workspace_tooling(tmp_path, project_name="Demo")

    assert payload["available"] is True
    assert payload["repo_profile"]["python_repo"] is True
    assert payload["repo_profile"]["node_repo"] is True
    assert "uv run pytest" in payload["validation_commands"]
    assert "pre-commit run --all-files" in payload["validation_commands"]
    assert "gitleaks dir . --redact" in payload["security_commands"]
    assert "rg --files" in payload["intake_commands"]
    tools = {tool["id"]: tool for tool in payload["tools"]}
    assert tools["ruff"]["configured"] is True
    assert tools["ruff"]["installed"] is True
    assert tools["playwright"]["configured"] is True
    assert tools["playwright"]["installed"] is False
    packs = {pack["id"]: pack for pack in payload["packs"]}
    assert packs["validation_evidence_pack"]["status"] == "needs_setup"
    assert "Install OSV-Scanner" in " ".join(payload["recommended_next_steps"])


def test_search_codebase_uses_ripgrep_when_available(monkeypatch, tmp_path: Path) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    project = Project(id=7, name="Demo", workspace_path=str(workspace), source_path=str(workspace))

    monkeypatch.setattr("manager.shutil.which", lambda command: "C:/tools/rg.exe" if command == "rg" else None)
    seen: dict[str, object] = {}

    class Result:
        returncode = 0
        stdout = "src/main.py:3:TODO wire validation lane\nREADME.md:9:TODO add docs\nsrc/worker.py:11:TODO add retry path\n"

    def fake_run(*args, **kwargs):
        seen["args"] = args
        seen["kwargs"] = kwargs
        return Result()

    monkeypatch.setattr("manager.subprocess.run", fake_run)

    payload = service.search_codebase(project, pattern="TODO", glob="*.py", max_matches=2)

    assert payload["search_backend"] == "ripgrep"
    assert payload["match_count"] == 2
    assert payload["matches"][0]["path"] == "src/main.py"
    assert payload["matches"][1]["path"] == "src/worker.py"
    assert payload["truncated"] is False
    assert payload["glob"] == "*.py"
    assert "path glob filter" in " ".join(payload["notes"]).lower()
    assert seen["args"] == (["C:/tools/rg.exe", "--line-number", "--with-filename", "-f", "-", "."],)
    assert seen["kwargs"]["input"] == "TODO\n"


def test_search_codebase_keeps_user_input_out_of_ripgrep_argv(monkeypatch, tmp_path: Path) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    project = Project(id=9, name="Safe Search", workspace_path=str(workspace), source_path=str(workspace))

    monkeypatch.setattr("manager.shutil.which", lambda command: "C:/tools/rg.exe" if command == "rg" else None)
    captured: dict[str, object] = {}

    class Result:
        returncode = 1
        stdout = ""

    def fake_run(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return Result()

    monkeypatch.setattr("manager.subprocess.run", fake_run)

    payload = service.search_codebase(project, pattern="--help", glob="--iglob=*", max_matches=5)

    assert payload["search_backend"] == "ripgrep"
    assert payload["match_count"] == 0
    assert captured["args"] == (["C:/tools/rg.exe", "--line-number", "--with-filename", "-f", "-", "."],)
    assert captured["kwargs"]["input"] == "--help\n"
    assert "--help" not in payload["command"]
    assert "--iglob=*" not in payload["command"]


def test_search_codebase_falls_back_without_ripgrep(monkeypatch, tmp_path: Path) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    (workspace / "app.py").write_text("print('alpha')\n# TODO ship\n", encoding="utf-8")
    project = Project(id=8, name="Fallback", workspace_path=str(workspace), source_path=str(workspace))

    monkeypatch.setattr("manager.shutil.which", lambda command: None)

    payload = service.search_codebase(project, pattern="TODO", max_matches=5)

    assert payload["search_backend"] == "python"
    assert payload["match_count"] == 1
    assert payload["matches"][0]["path"] == "app.py"
    assert "fell back" in " ".join(payload["notes"]).lower()


def test_detect_workspace_tooling_surfaces_tensorflow_product_pack(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname='tf-demo'\ndependencies=['tensorflow','tensorboard','tfx']\n",
        encoding="utf-8",
    )
    (tmp_path / "train.py").write_text("import tensorflow as tf\n", encoding="utf-8")
    (tmp_path / "export.py").write_text("import tensorflow as tf\n", encoding="utf-8")
    monkeypatch.setattr(
        "workspace_tooling._which",
        lambda command: f"C:/tools/{command}.exe" if command in {"tensorboard", "saved_model_cli", "tfx"} else None,
    )
    monkeypatch.setattr(
        "tensorflow_support.shutil.which",
        lambda command: f"C:/tools/{command}.exe" if command in {"tensorboard", "saved_model_cli", "tfx"} else None,
    )

    payload = detect_workspace_tooling(tmp_path, project_name="TensorFlow Demo")

    assert payload["repo_profile"]["tensorflow_repo"] is True
    assert payload["tensorflow_repo"]["enabled"] is True
    assert payload["tensorflow_validation_plan"]["available"] is True
    tools = {tool["id"]: tool for tool in payload["tools"]}
    assert tools["tensorboard"]["configured"] is True
    assert tools["tensorboard"]["installed"] is True
    assert tools["tfx"]["configured"] is True
    packs = {pack["id"]: pack for pack in payload["packs"]}
    assert packs["tensorflow_product_pack"]["status"] == "ready"
    assert "tensorboard --logdir logs" in payload["validation_commands"]


def test_detect_workspace_tooling_surfaces_pytorch_training_pack(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname='torch-demo'\ndependencies=['torch','torchvision','accelerate','transformers','onnx']\n",
        encoding="utf-8",
    )
    (tmp_path / "train.py").write_text("import torch\n", encoding="utf-8")
    (tmp_path / "export.py").write_text("import torch\n", encoding="utf-8")
    (tmp_path / "checkpoints").mkdir()
    (tmp_path / "checkpoints" / "model.pt").write_text("weights\n", encoding="utf-8")
    monkeypatch.setattr(
        "workspace_tooling._which",
        lambda command: f"C:/tools/{command}.exe" if command in {"torchrun", "tensorboard"} else None,
    )
    monkeypatch.setattr(
        "pytorch_support.shutil.which",
        lambda command: f"C:/tools/{command}.exe" if command in {"python", "torchrun"} else None,
    )
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
    monkeypatch.setattr(
        "workspace_tooling.detect_pytorch_runtime_status",
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

    payload = detect_workspace_tooling(tmp_path, project_name="PyTorch Demo")

    assert payload["repo_profile"]["pytorch_repo"] is True
    assert payload["pytorch_repo"]["enabled"] is True
    assert payload["pytorch_runtime_status"]["status"] == "ready"
    assert payload["pytorch_validation_plan"]["available"] is True
    tools = {tool["id"]: tool for tool in payload["tools"]}
    assert tools["torchrun"]["configured"] is True
    assert tools["torchrun"]["installed"] is True
    packs = {pack["id"]: pack for pack in payload["packs"]}
    assert packs["pytorch_training_pack"]["status"] == "ready"
    assert any(command.startswith("python train.py") for command in payload["validation_commands"])


def test_detect_workspace_tooling_uses_code_signals_and_survives_binary_config_files(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "requirements.txt").write_bytes(b"\xff\xfe\x00\x00")
    (tmp_path / "train.py").write_text(
        "import torch\nfrom torch.profiler import profile\nimport tensorflow as tf\n"
        "from keras.callbacks import TensorBoard\n"
        "tf.saved_model.save(object(), 'artifacts/exported_model')\n"
        "torchrun = 'enabled'\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "workspace_tooling._which",
        lambda command: f"C:/tools/{command}.exe" if command in {"tensorboard", "saved_model_cli", "torchrun"} else None,
    )
    monkeypatch.setattr(
        "workspace_tooling.detect_pytorch_runtime_status",
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

    payload = detect_workspace_tooling(tmp_path, project_name="Signal Demo")

    tools = {tool["id"]: tool for tool in payload["tools"]}
    assert tools["tensorboard"]["configured"] is True
    assert tools["saved_model_cli"]["configured"] is True
    assert tools["torchrun"]["configured"] is True
