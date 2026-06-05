from __future__ import annotations

from pathlib import Path

import pytest

from bridge_formatter import format_status_summary_message
from bridge_messages import bridge_runtime_service
from conftest import sample_workspace
from conftest import seed_imported_codebase_records
from gpu_support import detect_cuda_repo_mode, summarize_gpu_cluster_health


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


@pytest.fixture(autouse=True)
def _fast_gpu_runtime(monkeypatch) -> None:
    from orchestration import coordinator

    def fake_initial_scan(db, project, *, depth: str | None = None):
        return seed_imported_codebase_records(db, project, scan_depth=depth or "standard")

    async def fake_status_summary(db, project, orchestration=None):
        session = orchestration or coordinator.get_active_session_for_project(db, project)
        return format_status_summary_message(
            message_id=f"status-{project.id}-{session.id if session else 'project'}",
            project_id=project.id,
            orchestration_id=session.id if session else None,
            title="Mission Control status",
            summary="Status: fast GPU test stub.",
            project_name=project.name,
            manager_status="Waiting for dry-run command approval." if session is not None else "Ready to continue.",
            mode="dry_run / deterministic",
            swarm="not planned",
            user_action_needed="yes" if session is not None else "no",
            current_work=["Fast GPU orchestration test stub."],
            waiting_on_you=["Answer the pending decision."] if session is not None else [],
            next_expected_step="Continue the dry-run flow.",
            risk_level="medium" if session is not None else None,
            created_at=session.updated_at if session is not None else project.updated_at,
            orchestration_status=session.status if session is not None else project.status,
            current_blockers=[],
            handoff_readiness=project.handoff_status,
            active_agent_count=0,
            model_advisories=[],
        )

    original_start = coordinator.start_orchestration

    def fast_start_orchestration(
        db,
        *,
        project,
        source,
        user_request,
        orchestration_id=None,
        mode="unknown",
        metadata=None,
        schedule_background_turn=True,
    ):
        session = original_start(
            db,
            project=project,
            source=source,
            user_request=user_request,
            orchestration_id=orchestration_id,
            mode=mode,
            metadata=metadata,
            schedule_background_turn=False,
        )
        return session

    monkeypatch.setattr("imported_codebase.import_service.initial_scan", fake_initial_scan)
    monkeypatch.setattr(bridge_runtime_service, "get_status_summary", fake_status_summary)
    monkeypatch.setattr(coordinator, "start_orchestration", fast_start_orchestration)


def test_detect_cuda_repo_mode_finds_tile_signals_and_commands() -> None:
    workspace = Path(sample_workspace("cuda-tile-detect"))
    workspace.mkdir(parents=True, exist_ok=True)
    _write(
        workspace / "CMakeLists.txt",
        """
        cmake_minimum_required(VERSION 3.28)
        project(cuda_tile_demo LANGUAGES CXX CUDA)
        find_package(CUDAToolkit REQUIRED)
        # CUDA Tile programming path
        add_executable(tile_demo kernels/tile_demo.cu)
        """,
    )
    _write(workspace / "kernels" / "tile_demo.cu", "__global__ void kernel() {}\n")
    _write(workspace / "benchmarks" / "README.md", "benchmark target\n")

    payload = detect_cuda_repo_mode(workspace)

    assert payload["enabled"] is True
    assert payload["mode"] == "cuda_tile_cpp"
    assert "CUDA Tile" in payload["frameworks"]
    assert any(command.startswith("cmake -S . -B build") for command in payload["build_commands"])
    assert payload["benchmark_commands"]
    assert "benchmarks" in payload["important_paths"]


def test_detect_cuda_repo_mode_does_not_treat_readme_marketing_as_cuda_repo() -> None:
    workspace = Path(sample_workspace("cuda-readme-only"))
    workspace.mkdir(parents=True, exist_ok=True)
    _write(workspace / "README.md", "Mission Control can help with CUDA Tile, Nsight, and NVIDIA GPU workflows.\n")

    payload = detect_cuda_repo_mode(workspace)

    assert payload["enabled"] is False
    assert payload["mode"] is None


def test_detect_cuda_repo_mode_handles_deleted_workspace_gracefully() -> None:
    workspace = Path(sample_workspace("cuda-deleted-workspace"))
    workspace.mkdir(parents=True, exist_ok=True)
    workspace.rmdir()

    payload = detect_cuda_repo_mode(workspace)

    assert payload["enabled"] is False
    assert payload["mode"] is None


def test_gpu_cluster_health_flags_pending_pods_and_memory_pressure() -> None:
    workspace = Path(sample_workspace("gpu-health-blocked"))
    workspace.mkdir(parents=True, exist_ok=True)
    _write(workspace / "kernels" / "main.cu", "__global__ void kernel() {}\n")
    _write(
        workspace / ".mission-control" / "gpu" / "prometheus-summary.json",
        """
        {
          "source": "prometheus",
          "pending_pods": 3,
          "gpu_memory_utilization": 97,
          "notes": "insufficient nvidia.com/gpu"
        }
        """,
    )

    payload = summarize_gpu_cluster_health(workspace)

    assert payload["relevant"] is True
    assert payload["status"] == "degraded"
    assert payload["cluster_usable"] is False
    assert payload["pending_pod_count"] == 3
    assert payload["gpu_memory_saturated"] is True
    assert payload["likely_failure_source"] == "infrastructure"
    assert any("pending" in reason.lower() for reason in payload["blocking_reasons"])


def test_gpu_cluster_health_can_blame_code_when_cluster_looks_ready() -> None:
    workspace = Path(sample_workspace("gpu-health-code"))
    workspace.mkdir(parents=True, exist_ok=True)
    _write(workspace / "kernels" / "main.cu", "__global__ void kernel() {}\n")
    _write(
        workspace / ".mission-control" / "gpu" / "grafana-summary.txt",
        """
        Grafana panel export
        cluster_usable: true
        gpu_memory_utilization: 43
        pending_pods: 0
        """,
    )

    payload = summarize_gpu_cluster_health(workspace, failure_signals=["CUDA illegal memory access was reported by the test workload."])

    assert payload["status"] == "ready"
    assert payload["cluster_usable"] is True
    assert payload["likely_failure_source"] == "code"


def test_gpu_cluster_health_ignores_repo_source_files_that_only_sound_gpu_related() -> None:
    workspace = Path(sample_workspace("gpu-health-ignore-source-files"))
    workspace.mkdir(parents=True, exist_ok=True)
    _write(workspace / "gpu_support.py", "def helper():\n    return 'not observability'\n")
    _write(workspace / "nvidia_notes.md", "# NVIDIA notes\nThis is just documentation.\n")

    payload = summarize_gpu_cluster_health(workspace)

    assert payload["relevant"] is False
    assert payload["summary_files"] == []


def test_project_actions_surface_gpu_cluster_blockers(client) -> None:
    workspace = Path(sample_workspace("gpu-actions"))
    workspace.mkdir(parents=True, exist_ok=True)
    _write(workspace / "CMakeLists.txt", "project(cuda_demo LANGUAGES CXX CUDA)\nfind_package(CUDAToolkit REQUIRED)\n")
    _write(workspace / "kernels" / "main.cu", "__global__ void kernel() {}\n")
    _write(
        workspace / ".mission-control" / "gpu" / "summary.txt",
        """
        pending_pods: 4
        gpu_memory_utilization: 92
        insufficient nvidia.com/gpu
        """,
    )

    project = client.post(
        "/api/projects",
        json={
            "name": "GPU Status",
            "idea": "Track GPU blockers honestly.",
            "workspace_path": workspace.as_posix(),
            "provider": "codex",
            "runner_mode": "dry_run",
            "manager_mode": "deterministic",
        },
    ).json()

    actions = client.get(f"/api/projects/{project['id']}/actions").json()

    assert actions[0]["type"] == "degraded"
    assert "GPU cluster blocker" in actions[0]["message"]
    assert "infrastructure" in actions[0]["message"]


def test_orchestration_status_surfaces_gpu_blockers(client) -> None:
    workspace = Path(sample_workspace("gpu-orchestration"))
    workspace.mkdir(parents=True, exist_ok=True)
    _write(workspace / "CMakeLists.txt", "project(cuda_demo LANGUAGES CXX CUDA)\nfind_package(CUDAToolkit REQUIRED)\n")
    _write(workspace / "kernels" / "main.cu", "__global__ void kernel() {}\n")
    _write(workspace / ".mission-control" / "gpu" / "summary.txt", "pending_pods: 2\ninsufficient nvidia.com/gpu\n")

    project = client.post(
        "/api/projects",
        json={
            "name": "GPU Orchestration",
            "idea": "Surface GPU blockers in orchestration status.",
            "workspace_path": workspace.as_posix(),
            "provider": "codex",
            "runner_mode": "dry_run",
            "manager_mode": "deterministic",
        },
    ).json()
    orchestration = client.post(
        "/api/orchestrations",
        json={"project_id": project["id"], "user_request": "Investigate the CUDA failure.", "mode": "dry_run"},
    ).json()

    status = client.get(
        f"/api/orchestrations/{orchestration['id']}/status",
        params={"project_id": project["id"]},
    ).json()

    assert any("GPU cluster blocker" in blocker for blocker in status["current_blockers"])
