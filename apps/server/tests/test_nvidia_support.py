from __future__ import annotations

from nvidia_support import (
    detect_nvidia_aiq_status,
    detect_nvidia_dynamo_status,
    detect_nvidia_gpu_diagnostics,
    detect_project_nvidia_gpu_diagnostics,
    run_nvidia_aiq_research,
)


def test_detect_nvidia_dynamo_status_reports_reachable_frontend(monkeypatch) -> None:
    monkeypatch.setattr(
        "nvidia_support._json_request",
        lambda url, **kwargs: {"data": [{"id": "Qwen/Qwen3-0.6B"}]} if url.endswith("/v1/models") else {},
    )

    payload = detect_nvidia_dynamo_status("http://dynamo.local:8000")

    assert payload["reachable"] is True
    assert payload["endpoint"] == "http://dynamo.local:8000"
    assert payload["available_models"] == ["Qwen/Qwen3-0.6B"]
    assert payload["summary"].startswith("NVIDIA Dynamo frontend is reachable")


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
