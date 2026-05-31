from __future__ import annotations

from pathlib import Path

from conftest import sample_workspace
from tensorflow_support import build_tensorflow_validation_plan, detect_tensorflow_repo_mode


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_detect_tensorflow_repo_mode_finds_product_signals_and_commands() -> None:
    workspace = Path(sample_workspace("tensorflow-detect"))
    workspace.mkdir(parents=True, exist_ok=True)
    _write(
        workspace / "pyproject.toml",
        """
        [project]
        name = "tf-demo"
        dependencies = [
          "tensorflow>=2.18",
          "keras-tuner",
          "tensorboard",
          "tfx"
        ]
        """,
    )
    _write(workspace / "train.py", "import tensorflow as tf\n")
    _write(workspace / "export.py", "import tensorflow as tf\n")

    payload = detect_tensorflow_repo_mode(workspace)

    assert payload["enabled"] is True
    assert payload["mode"] == "tensorflow_tfx"
    assert "TensorFlow" in payload["frameworks"]
    assert "TensorBoard" in payload["frameworks"]
    assert "TFX" in payload["frameworks"]
    assert "python -m pip install -e ." in payload["build_commands"]
    assert "python train.py" in payload["training_commands"]
    assert "python export.py" in payload["export_commands"]
    assert "training_observability" in payload["product_workflows"]


def test_detect_tensorflow_repo_mode_does_not_treat_marketing_readme_as_repo_signal(tmp_path: Path) -> None:
    workspace = tmp_path / "tensorflow-readme-only"
    workspace.mkdir(parents=True, exist_ok=True)
    _write(workspace / "README.md", "Mission Control can help with TensorFlow, Keras, TFX, TensorBoard, and TensorFlow Lite.\n")

    payload = detect_tensorflow_repo_mode(workspace)

    assert payload["enabled"] is False
    assert payload["mode"] is None


def test_detect_tensorflow_repo_mode_handles_deleted_workspace_gracefully() -> None:
    workspace = Path(sample_workspace("tensorflow-deleted-workspace"))
    workspace.mkdir(parents=True, exist_ok=True)
    workspace.rmdir()

    payload = detect_tensorflow_repo_mode(workspace)

    assert payload["enabled"] is False
    assert payload["frameworks"] == []


def test_tensorflow_validation_plan_surfaces_export_and_observability_steps(monkeypatch) -> None:
    workspace = Path(sample_workspace("tensorflow-plan"))
    workspace.mkdir(parents=True, exist_ok=True)
    _write(
        workspace / "requirements.txt",
        """
        tensorflow
        tensorboard
        tensorflow-serving-api
        tflite-runtime
        pytest
        """,
    )
    _write(workspace / "train.py", "print('train')\n")
    _write(workspace / "export.py", "print('export')\n")

    monkeypatch.setattr(
        "tensorflow_support.shutil.which",
        lambda command: f"C:/tools/{command}.exe" if command in {"tensorboard", "saved_model_cli", "tflite_convert"} else None,
    )

    payload = build_tensorflow_validation_plan(workspace)

    assert payload["available"] is True
    assert payload["status"] == "ready"
    assert any(step["type"] == "train" for step in payload["steps"])
    assert any(step["type"] == "observability" for step in payload["steps"])
    assert any(step["type"] == "export" for step in payload["steps"])
    assert any("training, evaluation, and export" in target.lower() for target in payload["evidence_targets"])


def test_detect_tensorflow_repo_mode_ignores_artifact_flood_and_finds_real_repo_signals(tmp_path: Path) -> None:
    workspace = tmp_path / "artifact-heavy-tensorflow"
    (workspace / "artifacts").mkdir(parents=True, exist_ok=True)
    for index in range(1800):
        _write(workspace / "artifacts" / f"noise-{index}.txt", "x\n")
    _write(workspace / "pyproject.toml", "[project]\ndependencies=['tensorflow','tensorboard']\n")
    _write(workspace / "train.py", "import tensorflow as tf\n")

    payload = detect_tensorflow_repo_mode(workspace)

    assert payload["enabled"] is True
    assert "python train.py" in payload["training_commands"]
