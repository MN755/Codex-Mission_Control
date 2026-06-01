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
        json.dumps(
            {
                "devDependencies": {"@playwright/test": "^1.55.0"},
                "optionalDependencies": {"mlflow": "^2.0.0"},
                "peerDependencies": {"ruff": "^0.5.0"},
            }
        ),
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


def test_detect_workspace_tooling_returns_stable_contract_for_missing_workspace() -> None:
    payload = detect_workspace_tooling(None, project_name="Missing")

    assert payload["available"] is False
    assert payload["notebook_paths"] == []
    assert payload["notebook_commands"] == []
    assert payload["deployment_commands"] == []
    assert payload["artifact_paths"] == []
    assert payload["artifact_inspection_commands"] == []
    assert payload["config_review_paths"] == []
    assert payload["config_review_commands"] == []
    assert payload["tensorflow_repo"]["enabled"] is False
    assert payload["tensorflow_validation_plan"]["status"] == "not_applicable"
    assert payload["pytorch_repo"]["enabled"] is False
    assert payload["pytorch_runtime_status"]["status"] == "not_applicable"
    assert payload["pytorch_validation_plan"]["status"] == "not_applicable"


def test_detect_workspace_tooling_returns_stable_contract_for_invalid_workspace(tmp_path: Path) -> None:
    payload = detect_workspace_tooling(tmp_path / "does-not-exist", project_name="Invalid")

    assert payload["available"] is False
    assert payload["notebook_paths"] == []
    assert payload["notebook_commands"] == []
    assert payload["deployment_commands"] == []
    assert payload["artifact_paths"] == []
    assert payload["artifact_inspection_commands"] == []
    assert payload["config_review_paths"] == []
    assert payload["config_review_commands"] == []
    assert payload["tensorflow_repo"]["enabled"] is False
    assert payload["pytorch_repo"]["enabled"] is False


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
    assert "tensorboard --logdir artifacts/tensorboard" in payload["validation_commands"]


def test_detect_workspace_tooling_surfaces_pytorch_training_pack(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname='torch-demo'\ndependencies=['torch','torchvision','accelerate','transformers','onnx']\n",
        encoding="utf-8",
    )
    (tmp_path / "train.py").write_text("import torch\nimport accelerate\n", encoding="utf-8")
    (tmp_path / "export.py").write_text("import torch\n", encoding="utf-8")
    (tmp_path / "checkpoints").mkdir()
    (tmp_path / "checkpoints" / "model.pt").write_text("weights\n", encoding="utf-8")
    monkeypatch.setattr(
        "workspace_tooling._which",
        lambda command: f"C:/tools/{command}.exe" if command in {"accelerate", "tensorboard"} else None,
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
    assert tools["accelerate"]["configured"] is True
    assert tools["torchrun"]["configured"] is False
    packs = {pack["id"]: pack for pack in payload["packs"]}
    assert packs["pytorch_training_pack"]["status"] == "ready"
    assert any(command.startswith("python train.py") for command in payload["validation_commands"])


def test_detect_workspace_tooling_distinguishes_accelerate_from_torchrun(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname='torch-accelerate'\ndependencies=['torch','accelerate']\n",
        encoding="utf-8",
    )
    (tmp_path / "train.py").write_text("import accelerate\n", encoding="utf-8")
    monkeypatch.setattr(
        "workspace_tooling._which",
        lambda command: f"C:/tools/{command}.exe" if command == "accelerate" else None,
    )
    monkeypatch.setattr(
        "workspace_tooling.detect_pytorch_runtime_status",
        lambda _workspace: {
            "available": True,
            "status": "partial",
            "summary": "CPU-only runtime is fine for this check.",
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

    payload = detect_workspace_tooling(tmp_path, project_name="Accelerate Demo")

    tools = {tool["id"]: tool for tool in payload["tools"]}
    assert tools["accelerate"]["configured"] is True
    assert tools["accelerate"]["installed"] is True
    assert tools["torchrun"]["configured"] is False
    packs = {pack["id"]: pack for pack in payload["packs"]}
    assert packs["pytorch_training_pack"]["status"] == "ready"


def test_detect_workspace_tooling_surfaces_wandb_and_mlflow_signals(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='obs-demo'\n", encoding="utf-8")
    (tmp_path / "package.json").write_text(
        json.dumps({"optionalDependencies": {"mlflow": "^2.0.0"}, "peerDependencies": {"wandb": "^0.17.0"}}),
        encoding="utf-8",
    )
    (tmp_path / "train.py").write_text("import wandb\nimport mlflow\n", encoding="utf-8")
    monkeypatch.setattr(
        "workspace_tooling._which",
        lambda command: f"C:/tools/{command}.exe" if command in {"wandb", "mlflow"} else None,
    )

    payload = detect_workspace_tooling(tmp_path, project_name="Observability Demo")

    tools = {tool["id"]: tool for tool in payload["tools"]}
    assert tools["wandb"]["configured"] is True
    assert tools["wandb"]["installed"] is True
    assert tools["mlflow"]["configured"] is True
    assert tools["mlflow"]["installed"] is True


def test_detect_workspace_tooling_detects_nested_repo_profiles_and_lockfiles(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "apps" / "api").mkdir(parents=True, exist_ok=True)
    (tmp_path / "apps" / "web").mkdir(parents=True, exist_ok=True)
    (tmp_path / "services" / "rust").mkdir(parents=True, exist_ok=True)
    (tmp_path / "services" / "go").mkdir(parents=True, exist_ok=True)
    (tmp_path / "apps" / "api" / "pyproject.toml").write_text("[project]\nname='api'\n", encoding="utf-8")
    (tmp_path / "apps" / "api" / "uv.lock").write_text("version = 1\n", encoding="utf-8")
    (tmp_path / "apps" / "web" / "package.json").write_text(json.dumps({"name": "web"}), encoding="utf-8")
    (tmp_path / "apps" / "web" / "pnpm-lock.yaml").write_text("lockfileVersion: 9\n", encoding="utf-8")
    (tmp_path / "services" / "rust" / "Cargo.toml").write_text("[package]\nname='svc'\nversion='0.1.0'\n", encoding="utf-8")
    (tmp_path / "services" / "rust" / "Cargo.lock").write_text("# lock\n", encoding="utf-8")
    (tmp_path / "services" / "go" / "go.mod").write_text("module example.com/service\n", encoding="utf-8")
    (tmp_path / "services" / "go" / "go.sum").write_text("example.com dep\n", encoding="utf-8")
    monkeypatch.setattr("workspace_tooling._which", lambda _command: None)

    payload = detect_workspace_tooling(tmp_path, project_name="Monorepo")

    assert payload["repo_profile"]["python_repo"] is True
    assert payload["repo_profile"]["node_repo"] is True
    assert payload["repo_profile"]["rust_repo"] is True
    assert payload["repo_profile"]["go_repo"] is True
    assert "apps/api/uv.lock" in payload["repo_profile"]["lockfiles"]
    assert "apps/web/pnpm-lock.yaml" in payload["repo_profile"]["lockfiles"]
    assert "services/rust/Cargo.lock" in payload["repo_profile"]["lockfiles"]
    assert "services/go/go.sum" in payload["repo_profile"]["lockfiles"]


def test_detect_workspace_tooling_detects_nested_workspace_configs_and_packages(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "apps" / "api").mkdir(parents=True, exist_ok=True)
    (tmp_path / "apps" / "web").mkdir(parents=True, exist_ok=True)
    (tmp_path / "apps" / "api" / "pyproject.toml").write_text(
        "[project]\nname='api'\n[tool.ruff]\nline-length = 88\n",
        encoding="utf-8",
    )
    (tmp_path / "apps" / "api" / "noxfile.py").write_text("import nox\n", encoding="utf-8")
    (tmp_path / "apps" / "web" / "package.json").write_text(
        json.dumps(
            {
                "devDependencies": {"@playwright/test": "^1.55.0"},
                "optionalDependencies": {"mlflow": "^2.0.0"},
                "peerDependencies": {"wandb": "^0.17.0"},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "apps" / "web" / "playwright.config.ts").write_text("export default {};\n", encoding="utf-8")
    monkeypatch.setattr(
        "workspace_tooling._which",
        lambda command: f"C:/tools/{command}.exe" if command in {"ruff", "nox", "playwright", "wandb", "mlflow"} else None,
    )

    payload = detect_workspace_tooling(tmp_path, project_name="Nested Config Demo")

    tools = {tool["id"]: tool for tool in payload["tools"]}
    assert tools["ruff"]["configured"] is True
    assert "apps/api/pyproject.toml" in tools["ruff"]["config_files"]
    assert tools["nox"]["configured"] is True
    assert "apps/api/noxfile.py" in tools["nox"]["config_files"]
    assert tools["playwright"]["configured"] is True
    assert "apps/web/playwright.config.ts" in tools["playwright"]["config_files"]
    assert tools["wandb"]["configured"] is True
    assert "package.json::wandb" in tools["wandb"]["config_files"]
    assert tools["mlflow"]["configured"] is True
    assert "package.json::mlflow" in tools["mlflow"]["config_files"]


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


def test_detect_workspace_tooling_ignores_node_modules_signal_noise(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='clean-repo'\n", encoding="utf-8")
    node_modules = tmp_path / "node_modules" / "fake-package"
    node_modules.mkdir(parents=True, exist_ok=True)
    (node_modules / "index.js").write_text(
        "import wandb from 'wandb';\nimport mlflow from 'mlflow';\nconst token = 'tensorboard';\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("workspace_tooling._which", lambda _command: None)

    payload = detect_workspace_tooling(tmp_path, project_name="Noise Demo")

    tools = {tool["id"]: tool for tool in payload["tools"]}
    assert tools["wandb"]["configured"] is False
    assert tools["mlflow"]["configured"] is False
    assert tools["tensorboard"]["configured"] is False


def test_detect_workspace_tooling_reuses_repo_detection_results(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='reuse-demo'\ndependencies=['tensorflow','torch']\n", encoding="utf-8")
    tensorflow_calls = {"count": 0}
    pytorch_calls = {"count": 0}

    def fake_tensorflow(_root: Path) -> dict[str, object]:
        tensorflow_calls["count"] += 1
        return {"enabled": True, "mode": "tensorflow_product", "frameworks": ["TensorFlow"], "product_workflows": []}

    def fake_pytorch(_root: Path) -> dict[str, object]:
        pytorch_calls["count"] += 1
        return {"enabled": True, "mode": "pytorch_general", "frameworks": ["PyTorch"], "product_workflows": [], "distributed_stack": []}

    monkeypatch.setattr("workspace_tooling.detect_tensorflow_repo_mode", fake_tensorflow)
    monkeypatch.setattr("workspace_tooling.build_tensorflow_validation_plan", lambda _root: {"available": True, "status": "ready", "steps": [], "recommended_fixes": []})
    monkeypatch.setattr("workspace_tooling.detect_pytorch_repo_mode", fake_pytorch)
    monkeypatch.setattr("workspace_tooling.detect_pytorch_runtime_status", lambda _root: {"available": True, "status": "ready", "recommended_fixes": []})
    monkeypatch.setattr("workspace_tooling.build_pytorch_validation_plan", lambda _root: {"available": True, "status": "ready", "steps": [], "recommended_fixes": []})
    monkeypatch.setattr("workspace_tooling._which", lambda _command: None)

    payload = detect_workspace_tooling(tmp_path, project_name="Reuse Demo")

    assert payload["available"] is True
    assert tensorflow_calls["count"] == 1
    assert pytorch_calls["count"] == 1


def test_detect_workspace_tooling_includes_tensorflow_plan_commands_and_dedupes(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "requirements.txt").write_text("tensorflow\npytest\n", encoding="utf-8")
    (tmp_path / "train.py").write_text("import tensorflow as tf\n", encoding="utf-8")
    (tmp_path / "export.py").write_text("import tensorflow as tf\n", encoding="utf-8")
    monkeypatch.setattr("workspace_tooling._which", lambda command: "C:/tools/tensorboard.exe" if command == "tensorboard" else None)

    payload = detect_workspace_tooling(tmp_path, project_name="TensorFlow Commands")

    assert "python -m pytest" in payload["validation_commands"]
    assert "python train.py" in payload["validation_commands"]
    assert payload["validation_commands"].count("python -m pytest") == 1
    assert "python export.py" in payload["deployment_commands"]


def test_detect_workspace_tooling_reads_nested_project_text_signals(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "services" / "model").mkdir(parents=True, exist_ok=True)
    (tmp_path / "services" / "model" / "requirements.txt").write_text("tensorflow\ntensorboard\n", encoding="utf-8")
    monkeypatch.setattr(
        "workspace_tooling._which",
        lambda command: f"C:/tools/{command}.exe" if command == "tensorboard" else None,
    )

    payload = detect_workspace_tooling(tmp_path, project_name="Nested Text Demo")

    tools = {tool["id"]: tool for tool in payload["tools"]}
    assert tools["tensorboard"]["configured"] is True


def test_detect_workspace_tooling_prefers_concrete_tensorboard_command(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname='tf-demo'\ndependencies=['tensorflow','tensorboard']\n",
        encoding="utf-8",
    )
    (tmp_path / "train.py").write_text("from keras.callbacks import TensorBoard\n", encoding="utf-8")
    (tmp_path / "services" / "model" / "artifacts" / "tensorboard").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        "workspace_tooling._which",
        lambda command: f"C:/tools/{command}.exe" if command == "tensorboard" else None,
    )
    monkeypatch.setattr(
        "tensorflow_support.shutil.which",
        lambda command: f"C:/tools/{command}.exe" if command == "tensorboard" else None,
    )

    payload = detect_workspace_tooling(tmp_path, project_name="TensorBoard Demo")

    assert "tensorboard --logdir services/model/artifacts/tensorboard" in payload["validation_commands"]
    assert "tensorboard --logdir logs" not in payload["validation_commands"]


def test_detect_workspace_tooling_prefers_concrete_tensorflow_artifact_commands(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "requirements.txt").write_text("tensorflow\n", encoding="utf-8")
    (tmp_path / "saved_model.pb").write_text("artifact\n", encoding="utf-8")
    (tmp_path / "model.tflite").write_text("artifact\n", encoding="utf-8")
    monkeypatch.setattr(
        "workspace_tooling._which",
        lambda command: f"C:/tools/{command}.exe" if command in {"saved_model_cli", "tflite_convert"} else None,
    )
    monkeypatch.setattr(
        "tensorflow_support.shutil.which",
        lambda command: f"C:/tools/{command}.exe" if command in {"saved_model_cli", "tflite_convert"} else None,
    )

    payload = detect_workspace_tooling(tmp_path, project_name="TensorFlow Artifact Demo")

    assert "saved_model.pb" in " ".join(payload["artifact_paths"])
    assert "model.tflite" in " ".join(payload["artifact_paths"])
    assert "saved_model_cli show --dir . --all" in payload["deployment_commands"]
    assert any("model.tflite" in command and "size_bytes" in command for command in payload["deployment_commands"])
    assert "saved_model_cli show --dir <saved_model_dir> --all" not in payload["deployment_commands"]
    assert "saved_model_cli show --dir . --all" in payload["artifact_inspection_commands"]


def test_detect_workspace_tooling_surfaces_notebook_and_config_features(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "services" / "model").mkdir(parents=True, exist_ok=True)
    (tmp_path / "services" / "model" / "pyproject.toml").write_text(
        "[project]\nname='tf-nb'\ndependencies=['tensorflow']\n",
        encoding="utf-8",
    )
    (tmp_path / "services" / "model" / "train.py").write_text("import tensorflow as tf\n", encoding="utf-8")
    (tmp_path / "services" / "model" / "notebooks").mkdir(parents=True, exist_ok=True)
    (tmp_path / "services" / "model" / "configs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "services" / "model" / "notebooks" / "experiment.ipynb").write_text("{}\n", encoding="utf-8")
    (tmp_path / "services" / "model" / "configs" / "train.yaml").write_text("epochs: 4\n", encoding="utf-8")
    monkeypatch.setattr("workspace_tooling._which", lambda _command: None)

    payload = detect_workspace_tooling(tmp_path, project_name="Notebook Feature Demo")

    assert "services/model/notebooks/experiment.ipynb" in payload["notebook_paths"]
    assert "jupyter nbconvert --to script services/model/notebooks/experiment.ipynb" in payload["notebook_commands"]
    assert "services/model/configs/train.yaml" in payload["config_review_paths"]
    assert any("services/model/configs/train.yaml" in command for command in payload["config_review_commands"])
    assert "notebook flow(s) need scriptable rescue" in payload["summary"]
    packs = {pack["id"]: pack for pack in payload["packs"]}
    assert packs["notebook_recovery_pack"]["status"] == "needs_setup"
    assert packs["ml_config_audit_pack"]["status"] == "needs_setup"
