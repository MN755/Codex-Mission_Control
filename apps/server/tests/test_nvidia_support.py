from __future__ import annotations

from nvidia_support import (
    build_nvidia_validation_plan,
    detect_nvidia_aiq_status,
    detect_nvidia_dynamo_status,
    detect_nvidia_gpu_diagnostics,
    detect_nvidia_nim_status,
    detect_nvidia_local_runtime_status,
    detect_project_nvidia_gpu_diagnostics,
    run_nvidia_aiq_research,
)


def test_detect_nvidia_dynamo_status_reports_reachable_frontend(monkeypatch) -> None:
    monkeypatch.setattr(
        "nvidia_support._json_request",
        lambda url, **kwargs: {"data": [{"id": "Qwen/Qwen3-0.6B"}]} if url.endswith("/v1/models") else {},
    )

    payload = detect_nvidia_dynamo_status("http://dynamo.local:8000")

    assert payload["available"] is True
    assert payload["reachable"] is True
    assert payload["endpoint"] == "http://dynamo.local:8000"
    assert payload["available_models"] == ["Qwen/Qwen3-0.6B"]
    assert payload["summary"].startswith("NVIDIA Dynamo frontend is reachable")


def test_detect_nvidia_nim_status_normalizes_v1_endpoints(monkeypatch) -> None:
    monkeypatch.setattr(
        "nvidia_support._json_request",
        lambda url, **kwargs: {"data": [{"id": "meta/llama-3.1-8b-instruct"}]} if url.endswith("/v1/models") else {},
    )

    payload = detect_nvidia_nim_status("https://integrate.api.nvidia.com/v1")

    assert payload["available"] is True
    assert payload["endpoint"] == "https://integrate.api.nvidia.com"
    assert payload["available_models"] == ["meta/llama-3.1-8b-instruct"]


def test_detect_nvidia_aiq_status_reports_ready_stack(monkeypatch) -> None:
    def fake_object_request(url: str, **kwargs):
        if url.endswith("/health"):
            return {"status": "ok", "dask_available": True}
        if url.endswith("/v1/jobs/async/agents"):
            return {"agents": [{"agent_type": "deep_researcher"}]}
        raise AssertionError(url)

    monkeypatch.setattr("nvidia_support._json_request", fake_object_request)
    monkeypatch.setattr("nvidia_support._json_value_request", lambda url, **kwargs: [{"id": "pubmed"}])

    payload = detect_nvidia_aiq_status("http://aiq.local:8000")

    assert payload["available"] is True
    assert payload["install_status"] == "ready"
    assert payload["agent_types"] == ["deep_researcher"]
    assert payload["data_sources"] == ["pubmed"]


def test_run_nvidia_aiq_research_polls_until_success(monkeypatch) -> None:
    calls: list[str] = []

    def fake_request(url: str, **kwargs):
        calls.append(url)
        if url.endswith("/v1/jobs/async/submit"):
            return {"job_id": "job-123", "status": "SUBMITTED"}
        if url.endswith("/v1/jobs/async/job/job-123"):
            attempt = sum(1 for call in calls if call.endswith("/v1/jobs/async/job/job-123"))
            return {"job_id": "job-123", "status": "RUNNING" if attempt == 1 else "SUCCESS"}
        if url.endswith("/v1/jobs/async/job/job-123/report"):
            return {"report": "Use a retrieval-backed architecture."}
        if url.endswith("/v1/jobs/async/job/job-123/state"):
            return {
                "artifacts": {
                    "sources": {
                        "found": 3,
                        "cited": 2,
                        "cited_urls": ["https://example.com/a"],
                        "found_urls": ["https://example.com/a", "https://example.com/b"],
                    },
                    "tools": [{"name": "web-search", "status": "ok", "workflow": "research"}],
                }
            }
        raise AssertionError(url)

    monkeypatch.setattr("nvidia_support._json_request", fake_request)
    monkeypatch.setattr("nvidia_support.time.sleep", lambda _seconds: None)

    payload = run_nvidia_aiq_research(query="How should Mission Control validate CUDA services?")

    assert payload["status"] == "SUCCESS"
    assert payload["timed_out"] is False
    assert payload["job_id"] == "job-123"
    assert payload["source_summary"]["cited"] == 2
    assert payload["tools"][0]["name"] == "web-search"


def test_detect_nvidia_gpu_diagnostics_flags_cluster_pressure(monkeypatch) -> None:
    values = {
        "avg(DCGM_FI_DEV_GPU_UTIL)": 95.0,
        "sum(DCGM_FI_DEV_FB_USED)": 900.0,
        "sum(DCGM_FI_DEV_FB_FREE)": 50.0,
        "count(DCGM_FI_DEV_GPU_UTIL)": 2.0,
        'sum(kube_pod_status_phase{phase="Pending"})': 3.0,
        'sum(kube_pod_status_phase{phase="Running"})': 5.0,
    }
    monkeypatch.setattr("nvidia_support._prometheus_query", lambda base, query: values.get(query))

    payload = detect_nvidia_gpu_diagnostics("http://prometheus:9090")

    assert payload["available"] is True
    assert payload["status"] == "warning"
    assert any("Average GPU utilization" in item for item in payload["alerts"])
    assert any("Kubernetes pods are pending" in item for item in payload["alerts"])


def test_project_gpu_diagnostics_merge_workspace_summary_without_live_prometheus(tmp_path) -> None:
    workspace = tmp_path / "gpu-workspace"
    (workspace / "kernels").mkdir(parents=True, exist_ok=True)
    (workspace / "kernels" / "main.cu").write_text("__global__ void kernel() {}\n", encoding="utf-8")
    (workspace / ".mission-control" / "gpu").mkdir(parents=True, exist_ok=True)
    (workspace / ".mission-control" / "gpu" / "summary.txt").write_text(
        "pending_pods: 0\ngpu_memory_utilization: 44\n",
        encoding="utf-8",
    )

    payload = detect_project_nvidia_gpu_diagnostics(workspace)

    assert payload["available"] is True
    assert payload["workspace_relevant"] is True
    assert payload["status"] == "ready"
    assert payload["workspace_summary_status"] == "ready"
    assert payload["telemetry_status"] == "missing"
    assert payload["repo_mode"] == "cuda_cpp"


def test_project_gpu_diagnostics_merge_direct_telemetry_with_workspace_health(monkeypatch, tmp_path) -> None:
    values = {
        "avg(DCGM_FI_DEV_GPU_UTIL)": 95.0,
        "sum(DCGM_FI_DEV_FB_USED)": 900.0,
        "sum(DCGM_FI_DEV_FB_FREE)": 50.0,
        "count(DCGM_FI_DEV_GPU_UTIL)": 2.0,
        'sum(kube_pod_status_phase{phase="Pending"})': 1.0,
        'sum(kube_pod_status_phase{phase="Running"})': 5.0,
    }
    monkeypatch.setattr("nvidia_support._prometheus_query", lambda base, query: values.get(query))

    workspace = tmp_path / "gpu-workspace"
    (workspace / "kernels").mkdir(parents=True, exist_ok=True)
    (workspace / "kernels" / "main.cu").write_text("__global__ void kernel() {}\n", encoding="utf-8")
    (workspace / ".mission-control" / "gpu").mkdir(parents=True, exist_ok=True)
    (workspace / ".mission-control" / "gpu" / "summary.txt").write_text(
        "pending_pods: 0\ngpu_memory_utilization: 43\ncluster_usable: true\n",
        encoding="utf-8",
    )

    payload = detect_project_nvidia_gpu_diagnostics(workspace, prometheus_url="http://prometheus:9090")

    assert payload["available"] is True
    assert payload["status"] == "warning"
    assert payload["telemetry_status"] == "warning"
    assert payload["workspace_summary_status"] == "ready"
    assert payload["gpu_memory_saturated"] is True
    assert payload["likely_failure_source"] == "infrastructure"
    assert "Prometheus" in payload["observability_sources"]


def test_detect_nvidia_local_runtime_status_surfaces_partial_cuda_runtime(monkeypatch, tmp_path) -> None:
    workspace = tmp_path / "cuda-runtime"
    (workspace / "kernels").mkdir(parents=True, exist_ok=True)
    (workspace / "kernels" / "main.cu").write_text("__global__ void kernel() {}\n", encoding="utf-8")
    (workspace / "CMakeLists.txt").write_text(
        "project(cuda_demo LANGUAGES CXX CUDA)\nfind_package(CUDAToolkit REQUIRED)\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "nvidia_support.shutil.which",
        lambda command: {
            "nvidia-smi": "/usr/bin/nvidia-smi",
            "nvcc": "/usr/local/cuda/bin/nvcc",
            "compute-sanitizer": "/usr/local/cuda/bin/compute-sanitizer",
        }.get(command),
    )

    def fake_run(command: list[str], **kwargs):
        class Result:
            def __init__(self, stdout: str, returncode: int = 0) -> None:
                self.stdout = stdout
                self.stderr = ""
                self.returncode = returncode

        if command[-1] == "--version":
            return Result("Cuda compilation tools, release 13.3, V13.3.0")
        return Result("NVIDIA RTX PRO 4500, 555.42, 24564 MiB")

    monkeypatch.setattr("nvidia_support.subprocess.run", fake_run)

    payload = detect_nvidia_local_runtime_status(workspace)

    assert payload["available"] is True
    assert payload["repo_mode_enabled"] is True
    assert payload["status"] == "partial"
    assert payload["cuda_release"] == "13.3"
    assert payload["driver_version"] == "555.42"
    assert payload["compute_sanitizer_available"] is True
    assert payload["missing_optional_tools"]


def test_build_nvidia_validation_plan_combines_runtime_and_cluster_state(monkeypatch, tmp_path) -> None:
    workspace = tmp_path / "cuda-plan"
    (workspace / "kernels").mkdir(parents=True, exist_ok=True)
    (workspace / "kernels" / "main.cu").write_text("__global__ void kernel() {}\n", encoding="utf-8")
    (workspace / "CMakeLists.txt").write_text(
        "project(cuda_demo LANGUAGES CXX CUDA)\nfind_package(CUDAToolkit REQUIRED)\n",
        encoding="utf-8",
    )
    (workspace / ".mission-control" / "gpu").mkdir(parents=True, exist_ok=True)
    (workspace / ".mission-control" / "gpu" / "summary.txt").write_text("pending_pods: 2\ninsufficient nvidia.com/gpu\n", encoding="utf-8")

    monkeypatch.setattr(
        "nvidia_support.shutil.which",
        lambda command: {
            "nvidia-smi": "/usr/bin/nvidia-smi",
            "nvcc": "/usr/local/cuda/bin/nvcc",
            "compute-sanitizer": "/usr/local/cuda/bin/compute-sanitizer",
            "nsys": "/usr/bin/nsys",
            "docker": "/usr/bin/docker",
            "nvidia-ctk": "/usr/bin/nvidia-ctk",
            "ngc": "/usr/bin/ngc",
        }.get(command),
    )
    monkeypatch.setenv("MISSION_CONTROL_NVIDIA_NGC_SMOKE_IMAGE", "nvcr.io/nvidia/cuda:smoke")

    def fake_run(command: list[str], **kwargs):
        class Result:
            def __init__(self, stdout: str) -> None:
                self.stdout = stdout
                self.stderr = ""
                self.returncode = 0

        if command[-1] == "--version":
            return Result("Cuda compilation tools, release 13.3, V13.3.0")
        return Result("NVIDIA RTX PRO 4500, 555.42, 24564 MiB")

    monkeypatch.setattr("nvidia_support.subprocess.run", fake_run)

    payload = build_nvidia_validation_plan(workspace)

    assert payload["available"] is True
    assert payload["repo_mode_enabled"] is True
    assert payload["status"] == "blocked"
    assert payload["steps"]
    assert any(step["type"] == "sanitizer" for step in payload["steps"])
    assert any(step["type"] == "container_smoke" for step in payload["steps"])
    assert any("pending" in blocker.lower() for blocker in payload["blockers"])
