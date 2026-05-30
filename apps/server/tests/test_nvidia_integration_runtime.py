from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from conftest import sample_workspace
from nvidia_devstack import MockNvidiaStackConfig, start_mock_nvidia_stack
from nvidia_support import (
    build_nvidia_validation_plan,
    detect_nvidia_aiq_status,
    detect_nvidia_dynamo_status,
    detect_nvidia_nim_status,
    detect_project_nvidia_gpu_diagnostics,
    run_nvidia_aiq_research,
)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_nvidia_detectors_hit_real_mock_http_stack() -> None:
    stack = start_mock_nvidia_stack(MockNvidiaStackConfig())
    try:
        dynamo = detect_nvidia_dynamo_status(stack.dynamo_url)
        nim = detect_nvidia_nim_status(stack.nim_url)
        aiq = detect_nvidia_aiq_status(stack.aiq_url)
        research = run_nvidia_aiq_research(
            query="How should Mission Control validate CUDA services?",
            endpoint=stack.aiq_url,
            timeout_seconds=10,
            poll_interval_seconds=0.1,
        )
        assert dynamo["available"] is True
        assert nim["available"] is True
        assert aiq["available"] is True
        assert research["status"] == "SUCCESS"
    finally:
        stack.close()


def test_nvidia_project_endpoints_work_with_mock_stack(client, monkeypatch) -> None:
    stack = start_mock_nvidia_stack(MockNvidiaStackConfig())
    workspace = Path(sample_workspace("nvidia-endpoint-runtime"))
    workspace.mkdir(parents=True, exist_ok=True)
    _write(workspace / "CMakeLists.txt", "project(cuda_demo LANGUAGES CXX CUDA)\nfind_package(CUDAToolkit REQUIRED)\n")
    _write(workspace / "kernels" / "main.cu", "__global__ void kernel() {}\n")
    try:
        monkeypatch.setenv("MISSION_CONTROL_NVIDIA_DYNAMO_ENDPOINT", stack.dynamo_url)
        monkeypatch.setenv("MISSION_CONTROL_NVIDIA_NIM_ENDPOINT", stack.nim_url)
        monkeypatch.setenv("MISSION_CONTROL_NVIDIA_AIQ_ENDPOINT", stack.aiq_url)
        monkeypatch.setenv("MISSION_CONTROL_NVIDIA_PROMETHEUS_URL", stack.prometheus_url)

        project = client.post(
            "/api/projects",
            json={
                "name": "NVIDIA Runtime",
                "idea": "Exercise NVIDIA integration endpoints.",
                "workspace_path": workspace.as_posix(),
                "provider": "nvidia_dynamo",
                "runner_mode": "dry_run",
                "manager_mode": "deterministic",
            },
        ).json()

        dynamo = client.get(f"/api/projects/{project['id']}/nvidia/dynamo").json()
        nim = client.get(f"/api/projects/{project['id']}/nvidia/nim").json()
        aiq = client.get(f"/api/projects/{project['id']}/nvidia/aiq").json()
        gpu = client.get(f"/api/projects/{project['id']}/nvidia/gpu-diagnostics").json()
        local_runtime = client.get(f"/api/projects/{project['id']}/nvidia/local-runtime").json()
        validation_plan = client.get(f"/api/projects/{project['id']}/nvidia/validation-plan").json()

        assert dynamo["reachable"] is True
        assert nim["reachable"] is True
        assert aiq["available"] is True
        assert gpu["available"] is True
        assert local_runtime["repo_mode_enabled"] is True
        assert validation_plan["repo_mode_enabled"] is True
        assert validation_plan["steps"]
    finally:
        stack.close()


def test_nvidia_smoke_script_runs_against_mock_stack() -> None:
    workspace = Path(sample_workspace("nvidia-smoke-script"))
    workspace.mkdir(parents=True, exist_ok=True)
    _write(workspace / "CMakeLists.txt", "project(cuda_demo LANGUAGES CXX CUDA)\nfind_package(CUDAToolkit REQUIRED)\n")
    _write(workspace / "kernels" / "main.cu", "__global__ void kernel() {}\n")
    script = Path(__file__).resolve().parents[3] / "scripts" / "run_nvidia_stack_smoke.py"

    completed = subprocess.run(
        [sys.executable, str(script), "--mock-stack", "--workspace", workspace.as_posix()],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="ignore",
        check=False,
    )

    assert completed.returncode == 0, completed.stderr or completed.stdout
    payload = json.loads(completed.stdout)
    assert payload["dynamo_status"]["available"] is True
    assert payload["nim_status"]["available"] is True
    assert payload["aiq_status"]["available"] is True
    assert payload["validation_plan"]["repo_mode_enabled"] is True
