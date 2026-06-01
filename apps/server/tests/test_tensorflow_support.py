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
    assert payload["notebook_paths"] == []
    assert payload["config_paths"] == []
    assert payload["existing_savedmodel_artifacts"] == []
    assert payload["existing_tflite_artifacts"] == []


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


def test_detect_tensorflow_repo_mode_prioritizes_real_entrypoints_in_large_repo(tmp_path: Path) -> None:
    workspace = tmp_path / "tensorflow-priority-signals"
    workspace.mkdir(parents=True, exist_ok=True)
    _write(workspace / "pyproject.toml", "[project]\ndependencies=['tensorflow','tensorboard']\n")
    for index in range(40):
        _write(workspace / f"module_{index:02d}.py", "print('noise')\n")
    _write(workspace / "train.py", "import tensorflow as tf\nfrom keras.callbacks import TensorBoard\n")

    payload = detect_tensorflow_repo_mode(workspace)

    assert payload["enabled"] is True
    assert "TensorBoard" in payload["frameworks"]
    assert "python train.py" in payload["training_commands"]


def test_detect_tensorflow_repo_mode_discovers_nested_entrypoints_and_subproject_install(tmp_path: Path) -> None:
    workspace = tmp_path / "tensorflow-nested-entrypoints"
    workspace.mkdir(parents=True, exist_ok=True)
    _write(
        workspace / "services" / "model" / "pyproject.toml",
        "[project]\ndependencies=['tensorflow','tensorboard','tfx']\n",
    )
    _write(workspace / "services" / "model" / "train.py", "import tensorflow as tf\nfrom keras.callbacks import TensorBoard\n")
    _write(workspace / "services" / "model" / "tune.py", "import keras_tuner\n")
    _write(workspace / "services" / "model" / "export.py", "tf.saved_model.save\n")
    _write(workspace / "services" / "model" / "serve.py", "print('serve')\n")
    _write(workspace / "services" / "model" / "pipeline.py", "import tfx\n")

    payload = detect_tensorflow_repo_mode(workspace)

    assert "python -m pip install -e services/model" in payload["build_commands"]
    assert "python services/model/train.py" in payload["training_commands"]
    assert "python services/model/tune.py" in payload["training_commands"]
    assert "python services/model/pipeline.py" in payload["training_commands"]
    assert "python services/model/export.py" in payload["export_commands"]
    assert "python services/model/serve.py" in payload["export_commands"]


def test_detect_tensorflow_repo_mode_uses_real_nested_tensorboard_logdir(tmp_path: Path) -> None:
    workspace = tmp_path / "tensorflow-nested-logs"
    workspace.mkdir(parents=True, exist_ok=True)
    _write(workspace / "pyproject.toml", "[project]\ndependencies=['tensorflow','tensorboard']\n")
    _write(workspace / "train.py", "from keras.callbacks import TensorBoard\n",)
    (workspace / "services" / "model" / "artifacts" / "tensorboard").mkdir(parents=True, exist_ok=True)

    payload = detect_tensorflow_repo_mode(workspace)

    assert "tensorboard --logdir services/model/artifacts/tensorboard" in payload["observability_commands"]


def test_detect_tensorflow_repo_mode_tracks_notebooks_configs_and_artifacts(tmp_path: Path) -> None:
    workspace = tmp_path / "tensorflow-assets"
    workspace.mkdir(parents=True, exist_ok=True)
    _write(workspace / "services" / "model" / "pyproject.toml", "[project]\ndependencies=['tensorflow']\n")
    _write(workspace / "services" / "model" / "train.py", "import tensorflow as tf\n")
    _write(workspace / "services" / "model" / "notebooks" / "eda.ipynb", "{}\n")
    _write(workspace / "services" / "model" / "conf" / "train.yaml", "epochs: 5\n")
    _write(workspace / "services" / "model" / "artifacts" / "saved_model.pb", "artifact\n")
    _write(workspace / "services" / "model" / "artifacts" / "model.tflite", "artifact\n")

    payload = detect_tensorflow_repo_mode(workspace)

    assert "services/model/notebooks/eda.ipynb" in payload["notebook_paths"]
    assert "services/model/conf/train.yaml" in payload["config_paths"]
    assert "services/model/artifacts/saved_model.pb" in payload["existing_savedmodel_artifacts"]
    assert "services/model/artifacts/model.tflite" in payload["existing_tflite_artifacts"]


def test_detect_tensorflow_repo_mode_ignores_readme_hype_for_advanced_frameworks(tmp_path: Path) -> None:
    workspace = tmp_path / "tensorflow-readme-hype"
    workspace.mkdir(parents=True, exist_ok=True)
    _write(workspace / "pyproject.toml", "[project]\ndependencies=['tensorflow']\n")
    _write(workspace / "train.py", "import tensorflow as tf\n")
    _write(workspace / "README.md", "This repo definitely uses TFX, TensorBoard, TensorFlow Lite, and TensorFlow Hub.\n")

    payload = detect_tensorflow_repo_mode(workspace)

    assert payload["enabled"] is True
    assert "TFX" not in payload["frameworks"]
    assert "TensorBoard" not in payload["frameworks"]
    assert "TensorFlow Lite" not in payload["frameworks"]
    assert "TensorFlow Hub" not in payload["frameworks"]


def test_tensorflow_validation_plan_adds_sanity_step_and_export_fix(monkeypatch, tmp_path: Path) -> None:
    workspace = tmp_path / "tensorflow-export-signals"
    workspace.mkdir(parents=True, exist_ok=True)
    _write(workspace / "requirements.txt", "tensorflow\npytest\n")
    _write(workspace / "train.py", "import tensorflow as tf\n")
    _write(workspace / "notes.py", "tf.saved_model.save(model, 'artifacts/exported_model')\n")

    monkeypatch.setattr("tensorflow_support.shutil.which", lambda _command: None)

    payload = build_tensorflow_validation_plan(workspace)

    assert any(step["type"] == "sanity" and step["command"] == "python -m pytest" for step in payload["steps"])
    assert any("export entry point" in item.lower() for item in payload["recommended_fixes"])


def test_tensorflow_validation_plan_allows_export_only_repo(monkeypatch, tmp_path: Path) -> None:
    workspace = tmp_path / "tensorflow-export-only"
    workspace.mkdir(parents=True, exist_ok=True)
    _write(workspace / "requirements.txt", "tensorflow\n")
    _write(workspace / "export.py", "import tensorflow as tf\n")
    _write(workspace / "notes.py", "tf.saved_model.save(model, 'artifacts/exported_model')\n")

    monkeypatch.setattr("tensorflow_support.shutil.which", lambda _command: None)

    payload = build_tensorflow_validation_plan(workspace)

    assert payload["status"] == "ready"
    assert payload["blockers"] == []
    assert any(step["type"] == "export" and step["command"] == "python export.py" for step in payload["steps"])


def test_tensorflow_validation_plan_does_not_treat_placeholder_cli_export_as_real_execution(monkeypatch, tmp_path: Path) -> None:
    workspace = tmp_path / "tensorflow-placeholder-export"
    workspace.mkdir(parents=True, exist_ok=True)
    _write(workspace / "requirements.txt", "tensorflow\n",)
    _write(workspace / "notes.py", "tf.saved_model.save(model, 'artifacts/exported_model')\n")

    monkeypatch.setattr(
        "tensorflow_support.shutil.which",
        lambda command: f"C:/tools/{command}.exe" if command == "saved_model_cli" else None,
    )

    payload = build_tensorflow_validation_plan(workspace)

    assert payload["status"] == "blocked"
    assert any("repo-owned export entry point" in blocker.lower() for blocker in payload["blockers"])


def test_tensorflow_validation_plan_accepts_existing_artifacts_without_repo_export_command(monkeypatch, tmp_path: Path) -> None:
    workspace = tmp_path / "tensorflow-existing-artifacts"
    workspace.mkdir(parents=True, exist_ok=True)
    _write(workspace / "requirements.txt", "tensorflow\n",)
    _write(workspace / "saved_model.pb", "artifact\n")
    _write(workspace / "model.tflite", "artifact\n")

    monkeypatch.setattr(
        "tensorflow_support.shutil.which",
        lambda command: f"C:/tools/{command}.exe" if command in {"saved_model_cli", "tflite_convert"} else None,
    )

    payload = build_tensorflow_validation_plan(workspace)

    assert not any("deployment artifacts instead of just talking about them" in item for item in payload["recommended_fixes"])


def test_tensorflow_validation_plan_adds_concrete_artifact_inspection_steps(monkeypatch, tmp_path: Path) -> None:
    workspace = tmp_path / "tensorflow-artifact-inspection"
    workspace.mkdir(parents=True, exist_ok=True)
    _write(workspace / "requirements.txt", "tensorflow\n")
    _write(workspace / "saved_model.pb", "artifact\n")
    _write(workspace / "model.tflite", "artifact\n")

    monkeypatch.setattr(
        "tensorflow_support.shutil.which",
        lambda command: f"C:/tools/{command}.exe" if command == "saved_model_cli" else None,
    )

    payload = build_tensorflow_validation_plan(workspace)
    export_commands = [step["command"] for step in payload["steps"] if step["type"] == "export"]

    assert "saved_model_cli show --dir . --all" in export_commands
    assert any("model.tflite" in command and "size_bytes" in command for command in export_commands)


def test_tensorflow_validation_plan_calls_out_notebook_only_repo(monkeypatch, tmp_path: Path) -> None:
    workspace = tmp_path / "tensorflow-notebook-only"
    workspace.mkdir(parents=True, exist_ok=True)
    _write(workspace / "pyproject.toml", "[project]\ndependencies=['tensorflow']\n")
    _write(workspace / "notebooks" / "experiment.ipynb", "{}\n")

    monkeypatch.setattr("tensorflow_support.shutil.which", lambda _command: None)

    payload = build_tensorflow_validation_plan(workspace)

    assert payload["status"] == "blocked"
    assert any("notebook" in item.lower() and "repeatable" in item.lower() for item in payload["recommended_fixes"])
