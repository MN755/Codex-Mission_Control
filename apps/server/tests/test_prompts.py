from __future__ import annotations

from pathlib import Path

from conftest import sample_workspace
from models import Agent, Project, Task
from prompts import build_prompt_profile, manager_action_prompt, manager_interview_prompt, manager_swarm_prompt, worker_task_prompt


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_build_prompt_profile_prefers_compact_local_rules_for_small_ollama_model() -> None:
    profile = build_prompt_profile(provider="ollama", model="qwen2.5:7b", reasoning_effort="medium")

    assert profile.tier == "weak_local"
    assert profile.label == "compact local model"
    assert any("smallest valid output shape" in rule for rule in profile.manager_rules)


def test_manager_action_prompt_includes_elite_model_guidance() -> None:
    project = Project(name="Prompt Demo", idea="Ship a reliable backend flow", workspace_path=sample_workspace("prompt-manager"), status="draft", runner_mode="auto", manager_mode="auto")

    prompt = manager_action_prompt(
        project,
        docs_path=f"{project.workspace_path}/mission-control",
        action="plan.generate",
        objective="Produce a tight MVP plan.",
        response_schema={"summary_markdown": "string"},
        payload={"goal": "Fix the backend workflow."},
        user_name="Operator",
        provider="codex",
        model="gpt-5.5",
        reasoning_effort="high",
    )

    assert "Treat the current model as: elite planner." in prompt
    assert "evaluate multiple plausible approaches before choosing one" in prompt
    assert "These are default biases, not hard laws." in prompt


def test_manager_action_prompt_adds_compact_decomposition_biases_for_weak_model() -> None:
    project = Project(name="Prompt Demo", idea="Ship a reliable backend flow", workspace_path=sample_workspace("prompt-decompose"), status="draft", runner_mode="auto", manager_mode="auto")

    prompt = manager_action_prompt(
        project,
        docs_path=f"{project.workspace_path}/mission-control",
        action="tasks.decompose",
        objective="Turn the plan into execution-ready tasks.",
        response_schema={"summary_markdown": "string"},
        payload={"goal": "Fix the backend workflow."},
        user_name="Operator",
        provider="ollama",
        model="qwen2.5:7b",
        reasoning_effort="medium",
    )

    assert "Task-specific decision biases:" in prompt
    assert "Default to a compact task set with crisp titles and minimal overlap." in prompt
    assert "Prefer concrete path or subsystem boundaries over vague phases." in prompt


def test_manager_interview_prompt_adds_high_signal_biases_without_becoming_rigid() -> None:
    project = Project(name="Prompt Demo", idea="Build a local-first tool", workspace_path=sample_workspace("prompt-interview"), status="draft", runner_mode="auto", manager_mode="auto")

    prompt = manager_interview_prompt(
        project,
        action="interview.strategy",
        objective="Generate the first adaptive interview batch.",
        payload={"known": [], "unknowns": ["runtime", "scope"]},
        response_schema={"next_questions": []},
        user_name="Operator",
        provider="ollama",
        model="qwen2.5:7b",
        reasoning_effort="medium",
    )

    assert "Prefer 2-3 sharp questions in the next batch unless the payload makes more strictly necessary." in prompt
    assert "These are default biases, not hard laws." in prompt


def test_manager_swarm_prompt_adds_conservative_biases_for_weak_model() -> None:
    project = Project(name="Prompt Demo", idea="Parallelize a medium codebase safely", workspace_path=sample_workspace("prompt-swarm"), status="draft", runner_mode="auto", manager_mode="auto")

    prompt = manager_swarm_prompt(
        project,
        payload={"goal": "Parallelize work safely."},
        response_schema={"specs": []},
        user_name="Operator",
        provider="ollama",
        model="qwen2.5:7b",
        reasoning_effort="medium",
    )

    assert "Default to a conservative roster and low coordination complexity unless the payload strongly justifies expansion." in prompt
    assert "Avoid duplicate specialists unless their path ownership or mission is clearly different." in prompt


def test_manager_action_prompt_adds_existing_repo_biases_without_becoming_rigid() -> None:
    project = Project(
        name="Prompt Demo",
        idea="Fix a real codebase safely",
        workspace_path=sample_workspace("prompt-existing"),
        status="building",
        runner_mode="auto",
        manager_mode="auto",
        source_type="existing_folder",
        source_path=sample_workspace("prompt-existing"),
    )

    prompt = manager_action_prompt(
        project,
        docs_path=f"{project.workspace_path}/mission-control",
        action="plan.generate",
        objective="Generate a repair-oriented plan.",
        response_schema={"summary_markdown": "string"},
        payload={"goal": "Stabilize the existing repo."},
        user_name="Operator",
        provider="ollama",
        model="qwen2.5:7b",
        reasoning_effort="medium",
    )

    assert "Treat the repository as real inherited state." in prompt
    assert "Bias toward targeted repair, validation, and subsystem ownership" in prompt


def test_worker_task_prompt_includes_weak_model_guardrails() -> None:
    project = Project(name="Prompt Demo", idea="Fix a failing function", workspace_path=sample_workspace("prompt-worker"), status="building", runner_mode="auto", manager_mode="auto")
    agent = Agent(project_id=1, name="Worker", role="Implementation", kind="worker", status="idle", workspace_path=project.workspace_path)
    task = Task(
        id=2,
        project_id=1,
        title="Implement the smallest safe code fix",
        goal="Correct the failing behavior in the implementation.",
        scope="Update only the src implementation needed for the fix.",
        agent_role="Implementation",
        milestone="Milestone 1",
        allowed_paths_json=["src"],
        forbidden_paths_json=["docs"],
        validation_steps_json=["Run the focused test command"],
        success_criteria_json=["The expected behavior is restored"],
        estimated_complexity="small",
        dependencies_json=[],
        status="backlog",
        priority=10,
    )

    prompt = worker_task_prompt(
        project,
        agent,
        task,
        docs_path=f"{project.workspace_path}/mission-control",
        provider="ollama",
        model="qwen2.5:7b",
        reasoning_effort="medium",
    )

    assert "Treat the current model as: compact local model." in prompt
    assert "Favor one narrow change at a time" in prompt
    assert "Do not claim a fix, refactor, or validation result unless the output proves it directly." in prompt


def test_worker_task_prompt_adds_validation_biases_for_non_edit_task() -> None:
    project = Project(name="Prompt Demo", idea="Investigate a failure", workspace_path=sample_workspace("prompt-validate"), status="building", runner_mode="auto", manager_mode="auto")
    agent = Agent(project_id=1, name="Worker", role="Validation", kind="worker", status="idle", workspace_path=project.workspace_path)
    task = Task(
        id=3,
        project_id=1,
        title="Reproduce the failing behavior and isolate the smallest broken path",
        goal="Confirm the current failure locally.",
        scope="Inspect the repo and capture focused validation evidence.",
        agent_role="Validation",
        milestone="Milestone 1",
        allowed_paths_json=["src", "tests"],
        forbidden_paths_json=["docs"],
        validation_steps_json=["Run the focused test command"],
        success_criteria_json=["The failure is reproduced honestly"],
        estimated_complexity="small",
        dependencies_json=[],
        status="backlog",
        priority=10,
    )

    prompt = worker_task_prompt(
        project,
        agent,
        task,
        docs_path=f"{project.workspace_path}/mission-control",
        provider="ollama",
        model="qwen2.5:7b",
        reasoning_effort="medium",
    )

    assert "Do not claim file changes for reproduce, inspect, or validation work unless the task explicitly requires an edit." in prompt
    assert "Bias toward crisp evidence capture" in prompt


def test_worker_task_prompt_adds_project_state_biases_for_single_path_fix() -> None:
    project = Project(
        name="Prompt Demo",
        idea="Fix a narrow existing code path",
        workspace_path=sample_workspace("prompt-single-path"),
        status="building",
        runner_mode="auto",
        manager_mode="auto",
        source_type="existing_folder",
        source_path=sample_workspace("prompt-single-path"),
    )
    agent = Agent(project_id=1, name="Worker", role="Implementation", kind="worker", status="idle", workspace_path=project.workspace_path)
    task = Task(
        id=4,
        project_id=1,
        title="Implement a narrow fix",
        goal="Correct one broken implementation path.",
        scope="Touch only the service implementation.",
        agent_role="Implementation",
        milestone="Milestone 1",
        allowed_paths_json=["src/service"],
        forbidden_paths_json=["tests"],
        validation_steps_json=["Run the focused test command"],
        success_criteria_json=["The broken path is corrected"],
        estimated_complexity="small",
        dependencies_json=[],
        status="backlog",
        priority=10,
    )

    prompt = worker_task_prompt(
        project,
        agent,
        task,
        docs_path=f"{project.workspace_path}/mission-control",
        provider="ollama",
        model="qwen2.5:7b",
        reasoning_effort="medium",
    )

    assert "Treat the repository as real inherited state." in prompt
    assert "Path ownership is intentionally narrow here." in prompt


def test_worker_task_prompt_switches_into_gpu_programming_mode_for_cuda_repo() -> None:
    workspace = Path(sample_workspace("prompt-cuda"))
    workspace.mkdir(parents=True, exist_ok=True)
    _write(workspace / "CMakeLists.txt", "project(cuda_demo LANGUAGES CXX CUDA)\nfind_package(CUDAToolkit REQUIRED)\n")
    _write(workspace / "kernels" / "main.cu", "__global__ void kernel() {}\n")

    project = Project(name="Prompt Demo", idea="Tune a CUDA kernel", workspace_path=workspace.as_posix(), status="building", runner_mode="auto", manager_mode="auto")
    agent = Agent(project_id=1, name="GPU Worker", role="CUDA implementation", kind="worker", status="idle", workspace_path=project.workspace_path)
    task = Task(
        id=5,
        project_id=1,
        title="Optimize the CUDA kernel",
        goal="Improve the GPU kernel path without breaking correctness.",
        scope="Edit only the GPU kernel path and its focused validation loop.",
        agent_role="CUDA implementation",
        milestone="Milestone 1",
        allowed_paths_json=["kernels"],
        forbidden_paths_json=["docs"],
        validation_steps_json=["Build and run the focused GPU validation loop"],
        success_criteria_json=["The kernel path is validated honestly"],
        estimated_complexity="medium",
        dependencies_json=[],
        status="backlog",
        priority=10,
    )

    prompt = worker_task_prompt(
        project,
        agent,
        task,
        docs_path=f"{project.workspace_path}/mission-control",
        provider="codex",
        model="gpt-5.5",
        reasoning_effort="high",
    )

    assert "GPU programming mode:" in prompt
    assert "Treat CUDA and GPU validation as first-class work" in prompt
    assert "benchmark comparison, and Nsight profile loop" in prompt


def test_worker_task_prompt_switches_into_tensorflow_product_mode_for_tf_repo() -> None:
    workspace = Path(sample_workspace("prompt-tensorflow"))
    workspace.mkdir(parents=True, exist_ok=True)
    _write(
        workspace / "pyproject.toml",
        """
        [project]
        name = "tf_demo"
        dependencies = ["tensorflow", "tensorboard", "keras-tuner", "tensorflow-serving-api"]
        """,
    )
    _write(workspace / "train.py", "import tensorflow as tf\n")
    _write(workspace / "export.py", "import tensorflow as tf\n")
    _write(workspace / "notebooks" / "experiment.ipynb", "{}\n")
    _write(workspace / "configs" / "train.yaml", "epochs: 3\n")
    _write(workspace / "artifacts" / "saved_model.pb", "artifact\n")

    project = Project(name="Prompt Demo", idea="Ship a TensorFlow product path", workspace_path=workspace.as_posix(), status="building", runner_mode="auto", manager_mode="auto")
    agent = Agent(project_id=1, name="TF Worker", role="ML implementation", kind="worker", status="idle", workspace_path=project.workspace_path)
    task = Task(
        id=6,
        project_id=1,
        title="Implement the TensorFlow product flow",
        goal="Build, validate, and export the TensorFlow path honestly.",
        scope="Touch the training and export path only.",
        agent_role="ML implementation",
        milestone="Milestone 1",
        allowed_paths_json=["train.py", "export.py"],
        forbidden_paths_json=["docs"],
        validation_steps_json=["Run the focused TensorFlow validation loop"],
        success_criteria_json=["The TensorFlow path is validated honestly"],
        estimated_complexity="medium",
        dependencies_json=[],
        status="backlog",
        priority=10,
    )

    prompt = worker_task_prompt(
        project,
        agent,
        task,
        docs_path=f"{project.workspace_path}/mission-control",
        provider="codex",
        model="gpt-5.5",
        reasoning_effort="high",
    )

    assert "TensorFlow product mode:" in prompt
    assert "Treat data pipelines, training, evaluation, export, and serving checks as separate work" in prompt
    assert "TensorBoard" in prompt
    assert "Critical TensorFlow paths to keep in scope:" in prompt
    assert "Repo-owned TensorFlow execution entrypoints:" in prompt
    assert "Notebook rescue needed for:" in prompt
    assert "Review TensorFlow config files explicitly:" in prompt
    assert "Existing TensorFlow artifacts already in repo:" in prompt
    assert "TensorFlow artifact inspection commands already available:" in prompt
    assert "TensorFlow evidence to capture before claiming success:" in prompt


def test_worker_task_prompt_switches_into_pytorch_product_mode_for_torch_repo() -> None:
    workspace = Path(sample_workspace("prompt-pytorch"))
    workspace.mkdir(parents=True, exist_ok=True)
    _write(
        workspace / "pyproject.toml",
        """
        [project]
        name = "torch_demo"
        dependencies = ["torch", "torchvision", "accelerate", "transformers", "onnx"]
        """,
    )
    _write(workspace / "train.py", "import torch\n")
    _write(workspace / "export.py", "import torch\n")
    _write(workspace / "checkpoints" / "model.pt", "weights\n")
    _write(workspace / "artifacts" / "model.onnx", "artifact\n")
    _write(workspace / "notebooks" / "experiment.ipynb", "{}\n")
    _write(workspace / "configs" / "train.yaml", "epochs: 2\n")

    project = Project(name="Prompt Demo", idea="Ship a PyTorch product path", workspace_path=workspace.as_posix(), status="building", runner_mode="auto", manager_mode="auto")
    agent = Agent(project_id=1, name="Torch Worker", role="ML implementation", kind="worker", status="idle", workspace_path=project.workspace_path)
    task = Task(
        id=7,
        project_id=1,
        title="Implement the PyTorch product flow",
        goal="Build, validate, and export the PyTorch path honestly.",
        scope="Touch the training and export path only.",
        agent_role="ML implementation",
        milestone="Milestone 1",
        allowed_paths_json=["train.py", "export.py"],
        forbidden_paths_json=["docs"],
        validation_steps_json=["Run the focused PyTorch validation loop"],
        success_criteria_json=["The PyTorch path is validated honestly"],
        estimated_complexity="medium",
        dependencies_json=[],
        status="backlog",
        priority=10,
    )

    prompt = worker_task_prompt(
        project,
        agent,
        task,
        docs_path=f"{project.workspace_path}/mission-control",
        provider="codex",
        model="gpt-5.5",
        reasoning_effort="high",
    )

    assert "PyTorch product mode:" in prompt
    assert "Treat dataloaders, training, evaluation, checkpoints, and export as separate validation lanes" in prompt
    assert "device, precision, and batch size" in prompt
    assert "Critical PyTorch paths to keep in scope:" in prompt
    assert "Repo-owned PyTorch execution entrypoints:" in prompt
    assert "Notebook rescue needed for:" in prompt
    assert "Review PyTorch config files explicitly:" in prompt
    assert "Existing checkpoint evidence in repo:" in prompt
    assert "Existing PyTorch export artifacts already in repo:" in prompt
    assert "PyTorch artifact inspection commands already available:" in prompt
    assert "PyTorch evidence to capture before claiming success:" in prompt


def test_manager_action_prompt_surfaces_tensorflow_runtime_blockers_and_evidence(monkeypatch) -> None:
    import tensorflow_support

    project = Project(name="Prompt Demo", idea="Stabilize TensorFlow validation", workspace_path=sample_workspace("prompt-tf-blockers"), status="building", runner_mode="auto", manager_mode="auto")

    monkeypatch.setattr(
        tensorflow_support,
        "detect_tensorflow_repo_mode",
        lambda _: {
            "enabled": True,
            "mode": "tensorflow_product",
            "frameworks": ["TensorFlow", "SavedModel / Serving"],
            "product_workflows": ["training", "serving_export"],
            "important_paths": ["train.py", "artifacts/exported_model/saved_model.pb"],
            "notebook_paths": [],
            "config_paths": [],
            "existing_savedmodel_artifacts": ["artifacts/exported_model/saved_model.pb"],
            "existing_tflite_artifacts": [],
        },
    )
    monkeypatch.setattr(
        tensorflow_support,
        "build_tensorflow_validation_plan",
        lambda _: {
            "available": True,
            "status": "blocked",
            "steps": [
                {"title": "Run the training or pipeline entry point", "command": "python train.py", "type": "train", "status": "pending"},
                {"title": "Inspect the existing SavedModel artifact", "command": "saved_model_cli show --dir artifacts/exported_model --all", "type": "export", "status": "pending"},
            ],
            "blockers": ["Python is not available on PATH for the repo-owned TensorFlow commands this workspace expects to run."],
            "recommended_fixes": ["Expose Python on PATH before asking Mission Control to run repo-owned TensorFlow validation commands."],
            "evidence_targets": ["Show the produced artifact path for SavedModel exports when deployment claims are made."],
            "product_workflows": ["training", "serving_export"],
        },
    )

    prompt = manager_action_prompt(
        project,
        docs_path=f"{project.workspace_path}/mission-control",
        action="plan.generate",
        objective="Generate the next TensorFlow validation plan.",
        response_schema={"summary_markdown": "string"},
        payload={"goal": "Fix the TensorFlow path honestly."},
        user_name="Operator",
        provider="codex",
        model="gpt-5.5",
        reasoning_effort="high",
    )

    assert "Critical TensorFlow paths to keep in scope:" in prompt
    assert "Repo-owned TensorFlow execution entrypoints:" in prompt
    assert "TensorFlow artifact inspection commands already available:" in prompt
    assert "TensorFlow runtime blockers right now:" in prompt
    assert "TensorFlow evidence to capture before claiming success:" in prompt


def test_manager_action_prompt_surfaces_pytorch_runtime_blockers_and_evidence(monkeypatch) -> None:
    import pytorch_support

    project = Project(name="Prompt Demo", idea="Stabilize PyTorch validation", workspace_path=sample_workspace("prompt-torch-blockers"), status="building", runner_mode="auto", manager_mode="auto")

    monkeypatch.setattr(
        pytorch_support,
        "detect_pytorch_repo_mode",
        lambda _: {
            "enabled": True,
            "mode": "pytorch_distributed",
            "frameworks": ["TorchVision", "Accelerate"],
            "product_workflows": ["distributed_training", "model_export"],
            "important_paths": ["train.py", "artifacts/model.onnx"],
            "notebook_paths": [],
            "config_paths": [],
            "checkpoint_paths": ["checkpoints/model.pt"],
            "existing_onnx_artifacts": ["artifacts/model.onnx"],
            "existing_torchscript_artifacts": [],
        },
    )
    monkeypatch.setattr(
        pytorch_support,
        "build_pytorch_validation_plan",
        lambda _: {
            "available": True,
            "status": "blocked",
            "runtime_status": "blocked",
            "steps": [
                {"title": "Run the training entry point", "command": "python train.py", "type": "train", "status": "pending"},
                {"title": "Inspect existing checkpoints", "command": "python -c \"print('checkpoint')\"", "type": "checkpoint", "status": "pending"},
                {"title": "Inspect existing ONNX export artifact", "command": "python -c \"print('onnx')\"", "type": "export", "status": "pending"},
            ],
            "blockers": ["Python is not available on PATH for the repo-owned PyTorch validation commands in this plan."],
            "recommended_fixes": ["Expose Python on PATH before running the generated PyTorch validation lane."],
            "evidence_targets": ["Show checkpoint artifact paths and whether resume or load actually succeeded."],
            "product_workflows": ["distributed_training", "model_export"],
        },
    )

    prompt = manager_action_prompt(
        project,
        docs_path=f"{project.workspace_path}/mission-control",
        action="plan.generate",
        objective="Generate the next PyTorch validation plan.",
        response_schema={"summary_markdown": "string"},
        payload={"goal": "Fix the PyTorch path honestly."},
        user_name="Operator",
        provider="codex",
        model="gpt-5.5",
        reasoning_effort="high",
    )

    assert "Critical PyTorch paths to keep in scope:" in prompt
    assert "Repo-owned PyTorch execution entrypoints:" in prompt
    assert "PyTorch artifact inspection commands already available:" in prompt
    assert "PyTorch runtime blockers right now:" in prompt
    assert "PyTorch evidence to capture before claiming success:" in prompt
