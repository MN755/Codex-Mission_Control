from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote_plus
from urllib.request import Request, urlopen

from gpu_support import detect_cuda_repo_mode, summarize_gpu_cluster_health


DEFAULT_NVIDIA_DYNAMO_ENDPOINT = "http://localhost:8000"
DEFAULT_NVIDIA_NIM_ENDPOINT = "https://integrate.api.nvidia.com"
DEFAULT_NVIDIA_AIQ_ENDPOINT = "http://localhost:8000"
DEFAULT_NVIDIA_SMOKE_QUERY = "How should Mission Control validate a CUDA-backed code change?"


def _string_list(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        ordered.append(text)
    return ordered


def _env_first(*keys: str) -> str | None:
    for key in keys:
        value = str(os.environ.get(key) or "").strip()
        if value:
            return value
    return None


def _normalize_base_url(value: str | None, *, default: str) -> tuple[str, bool]:
    configured = bool(str(value or "").strip())
    base = (str(value or "").strip() or default).rstrip("/")
    return base, configured


def _normalize_openai_frontend_base_url(value: str | None, *, default: str) -> tuple[str, bool]:
    base, configured = _normalize_base_url(value, default=default)
    if base.lower().endswith("/v1"):
        base = base[:-3].rstrip("/")
    return base, configured


def _json_request(
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 8.0,
) -> dict[str, Any]:
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8") if payload is not None else None,
        headers={"Accept": "application/json", **(headers or {})},
        method=method,
    )
    with urlopen(request, timeout=timeout) as response:
        body = response.read().decode("utf-8", errors="ignore")
    loaded = json.loads(body or "{}")
    if not isinstance(loaded, dict):
        raise RuntimeError("Expected a JSON object response.")
    return loaded


def _json_value_request(
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 8.0,
) -> Any:
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8") if payload is not None else None,
        headers={"Accept": "application/json", **(headers or {})},
        method=method,
    )
    with urlopen(request, timeout=timeout) as response:
        body = response.read().decode("utf-8", errors="ignore")
    return json.loads(body or "null")


def _bearer_headers(api_key: str | None) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    token = str(api_key or "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _extract_openai_models(payload: dict[str, Any]) -> list[str]:
    data = payload.get("data")
    if not isinstance(data, list):
        return []
    return _string_list([item.get("id") for item in data if isinstance(item, dict)])


def _openai_frontend_status(
    *,
    provider: str,
    label: str,
    endpoint: str | None,
    default_endpoint: str,
    endpoint_env_keys: tuple[str, ...],
    api_key_env_keys: tuple[str, ...],
    notes: list[str],
) -> dict[str, Any]:
    configured_endpoint = endpoint or _env_first(*endpoint_env_keys)
    base, endpoint_configured = _normalize_openai_frontend_base_url(configured_endpoint, default=default_endpoint)
    api_key = _env_first(*api_key_env_keys)
    reachable = False
    auth_required = False
    available_models: list[str] = []
    summary = f"{label} is not reachable at {base}."
    try:
        payload = _json_request(f"{base}/v1/models", headers=_bearer_headers(api_key), timeout=4.0)
        available_models = _extract_openai_models(payload)
        reachable = True
        summary = f"{label} is reachable at {base}."
    except HTTPError as exc:
        if exc.code in {401, 403}:
            reachable = True
            auth_required = True
            summary = f"{label} is reachable at {base}, but it requires authentication."
    except (URLError, TimeoutError, OSError, json.JSONDecodeError, RuntimeError):
        reachable = False
    authenticated = reachable and (not auth_required or bool(api_key))
    available = reachable and authenticated
    return {
        "provider": provider,
        "label": label,
        "available": available,
        "cli_detected": reachable or endpoint_configured,
        "cli_path": base,
        "cli_path_exists": reachable or endpoint_configured,
        "cli_execution_available": reachable,
        "cli_version": base if reachable else None,
        "login_status": summary,
        "auth_mode": "api_key" if api_key else ("optional" if not auth_required else None),
        "authenticated": authenticated,
        "auth_status_detectable": True,
        "supports_model_override": True,
        "supports_reasoning_effort": False,
        "supports_app_server": False,
        "supports_builtin_auth": False,
        "available_models": available_models,
        "notes": notes,
        "reachable": reachable,
        "summary": summary,
        "endpoint": base,
        "endpoint_configured": endpoint_configured,
        "api_key_configured": bool(api_key),
        "auth_required": auth_required,
    }


def _run_command(command: list[str], *, timeout: float = 6.0) -> tuple[int | None, str]:
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError, TimeoutError):
        return None, ""
    return completed.returncode, "\n".join(part for part in [completed.stdout, completed.stderr] if part).strip()


def _extract_nvcc_release(text: str) -> str | None:
    match = re.search(r"release\s+([0-9]+(?:\.[0-9]+)*)", text, flags=re.IGNORECASE)
    return match.group(1) if match else None


def _extract_driver_version(text: str) -> str | None:
    match = re.search(r"driver[_ -]?version[^0-9]*([0-9]+(?:\.[0-9]+)*)", text, flags=re.IGNORECASE)
    return match.group(1) if match else None


def _parse_nvidia_smi_csv(text: str) -> tuple[list[str], str | None]:
    names: list[str] = []
    driver_version: str | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = [part.strip() for part in line.split(",")]
        if parts and parts[0]:
            names.append(parts[0])
        if len(parts) > 1 and parts[1] and driver_version is None:
            driver_version = parts[1]
    if driver_version is None:
        driver_version = _extract_driver_version(text)
    return _string_list(names), driver_version


def detect_nvidia_dynamo_status(endpoint: str | None = None) -> dict[str, Any]:
    notes = [
        "NVIDIA Dynamo exposes an OpenAI-compatible frontend and fits Mission Control as a GPU-backed worker-provider lane.",
        "Mission Control treats Dynamo as optional infrastructure for higher-throughput coding swarms, not as a required local dependency.",
    ]
    payload = _openai_frontend_status(
        provider="nvidia_dynamo",
        label="NVIDIA Dynamo frontend",
        endpoint=endpoint,
        default_endpoint=DEFAULT_NVIDIA_DYNAMO_ENDPOINT,
        endpoint_env_keys=("MISSION_CONTROL_NVIDIA_DYNAMO_ENDPOINT", "NVIDIA_DYNAMO_ENDPOINT"),
        api_key_env_keys=("MISSION_CONTROL_NVIDIA_DYNAMO_API_KEY", "NVIDIA_DYNAMO_API_KEY"),
        notes=list(notes),
    )
    if payload["auth_required"] and not payload["api_key_configured"]:
        notes.append("Set NVIDIA_DYNAMO_API_KEY or MISSION_CONTROL_NVIDIA_DYNAMO_API_KEY if your Dynamo frontend requires bearer auth.")
    if not payload["endpoint_configured"]:
        notes.append("No explicit Dynamo endpoint is configured, so Mission Control is probing the default localhost frontend.")
    payload["notes"] = notes
    payload["label"] = "NVIDIA Dynamo"
    return payload


def detect_nvidia_nim_status(endpoint: str | None = None) -> dict[str, Any]:
    notes = [
        "NVIDIA NIM exposes deployable inference microservices that fit Mission Control as a self-hosted or hosted GPU-backed worker-provider lane.",
        "Mission Control treats NIM as an OpenAI-compatible inference surface for coding, review, and validation agents when NVIDIA-hosted or self-hosted endpoints are available.",
    ]
    configured_endpoint = endpoint or _env_first("MISSION_CONTROL_NVIDIA_NIM_ENDPOINT", "NVIDIA_NIM_ENDPOINT")
    configured_api_key = _env_first("MISSION_CONTROL_NVIDIA_NIM_API_KEY", "NVIDIA_NIM_API_KEY")
    if not configured_endpoint and not configured_api_key:
        notes.append("No explicit NIM endpoint or API key is configured, so Mission Control is not probing hosted NIM by default.")
        return {
            "provider": "nvidia_nim",
            "label": "NVIDIA NIM",
            "available": False,
            "cli_detected": False,
            "cli_path": DEFAULT_NVIDIA_NIM_ENDPOINT,
            "cli_path_exists": False,
            "cli_execution_available": False,
            "cli_version": None,
            "login_status": "NVIDIA NIM is not configured for this runtime yet.",
            "auth_mode": None,
            "authenticated": False,
            "auth_status_detectable": True,
            "supports_model_override": True,
            "supports_reasoning_effort": False,
            "supports_app_server": False,
            "supports_builtin_auth": False,
            "available_models": [],
            "notes": notes,
            "reachable": False,
            "summary": "NVIDIA NIM is not configured for this runtime yet.",
            "endpoint": DEFAULT_NVIDIA_NIM_ENDPOINT,
            "endpoint_configured": False,
            "api_key_configured": False,
            "auth_required": True,
        }
    payload = _openai_frontend_status(
        provider="nvidia_nim",
        label="NVIDIA NIM",
        endpoint=configured_endpoint,
        default_endpoint=DEFAULT_NVIDIA_NIM_ENDPOINT,
        endpoint_env_keys=("MISSION_CONTROL_NVIDIA_NIM_ENDPOINT", "NVIDIA_NIM_ENDPOINT"),
        api_key_env_keys=("MISSION_CONTROL_NVIDIA_NIM_API_KEY", "NVIDIA_NIM_API_KEY"),
        notes=list(notes),
    )
    if payload["auth_required"] and not payload["api_key_configured"]:
        notes.append("Set NVIDIA_NIM_API_KEY or MISSION_CONTROL_NVIDIA_NIM_API_KEY before routing Mission Control workers into an authenticated NIM deployment.")
    if not payload["endpoint_configured"]:
        notes.append("No explicit NIM endpoint is configured, so Mission Control falls back to the hosted NVIDIA integrate endpoint shape.")
    payload["notes"] = notes
    payload["label"] = "NVIDIA NIM"
    return payload


def detect_nvidia_aiq_status(endpoint: str | None = None) -> dict[str, Any]:
    configured_endpoint = endpoint or _env_first("MISSION_CONTROL_NVIDIA_AIQ_ENDPOINT", "NVIDIA_AIQ_ENDPOINT")
    base, endpoint_configured = _normalize_base_url(configured_endpoint, default=DEFAULT_NVIDIA_AIQ_ENDPOINT)
    api_key = _env_first("MISSION_CONTROL_NVIDIA_AIQ_API_KEY", "NVIDIA_AIQ_API_KEY")
    notes = [
        "NVIDIA AI-Q is a deep-research system built on the NeMo Agent Toolkit with an async jobs API.",
        "Mission Control uses AI-Q as an optional research delegation lane for cited architecture, dependency, and implementation research.",
    ]
    reachable = False
    auth_required = False
    dask_available: bool | None = None
    agent_types: list[str] = []
    data_sources: list[str] = []
    summary = f"NVIDIA AI-Q endpoint is not reachable at {base}."
    headers = _bearer_headers(api_key)
    try:
        health = _json_request(f"{base}/health", headers=headers, timeout=4.0)
        reachable = str(health.get("status") or "").lower() == "ok"
        dask_available = bool(health.get("dask_available")) if "dask_available" in health else None
        agents = _json_request(f"{base}/v1/jobs/async/agents", headers=headers, timeout=4.0)
        raw_agents = agents.get("agents") if isinstance(agents, dict) else []
        if isinstance(raw_agents, list):
            agent_types = _string_list([item.get("agent_type") for item in raw_agents if isinstance(item, dict)])
        try:
            sources = _json_value_request(f"{base}/v1/data_sources", headers=headers, timeout=4.0)
            if isinstance(sources, list):
                data_sources = _string_list([item.get("id") for item in sources if isinstance(item, dict)])
            elif isinstance(sources, dict):
                data_sources = _string_list([item.get("id") for item in list(sources.get("data_sources") or []) if isinstance(item, dict)])
        except Exception:
            data_sources = []
        if reachable:
            summary = f"NVIDIA AI-Q endpoint is reachable at {base}."
        elif dask_available is False:
            summary = f"NVIDIA AI-Q endpoint responded at {base}, but its Dask worker stack is not available."
    except HTTPError as exc:
        if exc.code in {401, 403}:
            reachable = True
            auth_required = True
            summary = f"NVIDIA AI-Q endpoint is reachable at {base}, but it requires authentication."
            notes.append("Set NVIDIA_AIQ_API_KEY or MISSION_CONTROL_NVIDIA_AIQ_API_KEY if your AI-Q deployment uses bearer auth.")
    except (URLError, TimeoutError, OSError, json.JSONDecodeError, RuntimeError):
        reachable = False
    available = reachable and (dask_available is not False) and (not auth_required or bool(api_key))
    install_status = "ready" if available else ("partial" if reachable else "missing")
    recommended_fix = None
    if not endpoint_configured:
        recommended_fix = "Set MISSION_CONTROL_NVIDIA_AIQ_ENDPOINT or NVIDIA_AIQ_ENDPOINT to a running AI-Q web deployment."
    elif not reachable:
        recommended_fix = "Start AI-Q in web mode so the REST API is exposed before routing Mission Control research into it."
    elif dask_available is False:
        recommended_fix = "Bring the AI-Q Dask worker stack online before expecting deep research jobs to complete."
    return {
        "available": available,
        "install_status": install_status,
        "summary": summary,
        "endpoint": base,
        "endpoint_configured": endpoint_configured,
        "api_key_configured": bool(api_key),
        "auth_required": auth_required,
        "dask_available": dask_available,
        "agent_types": agent_types,
        "data_sources": data_sources,
        "recommended_fix": recommended_fix,
        "notes": notes,
    }


def run_nvidia_aiq_research(
    *,
    query: str,
    agent_type: str = "deep_researcher",
    endpoint: str | None = None,
    timeout_seconds: int = 90,
    poll_interval_seconds: float = 2.0,
    expiry_seconds: int = 3600,
) -> dict[str, Any]:
    prompt = str(query or "").strip()
    if not prompt:
        raise RuntimeError("AI-Q research requires a non-empty query.")
    configured_endpoint = endpoint or _env_first("MISSION_CONTROL_NVIDIA_AIQ_ENDPOINT", "NVIDIA_AIQ_ENDPOINT")
    base, _ = _normalize_base_url(configured_endpoint, default=DEFAULT_NVIDIA_AIQ_ENDPOINT)
    api_key = _env_first("MISSION_CONTROL_NVIDIA_AIQ_API_KEY", "NVIDIA_AIQ_API_KEY")
    headers = _bearer_headers(api_key)
    submit = _json_request(
        f"{base}/v1/jobs/async/submit",
        method="POST",
        headers=headers,
        payload={"agent_type": agent_type, "input": prompt, "expiry_seconds": int(expiry_seconds)},
        timeout=10.0,
    )
    job_id = str(submit.get("job_id") or "").strip()
    if not job_id:
        raise RuntimeError("AI-Q submit response did not include a job_id.")
    deadline = time.monotonic() + max(int(timeout_seconds), 5)
    poll_count = 0
    latest_status_payload: dict[str, Any] = dict(submit)
    final_status = str(submit.get("status") or "SUBMITTED").upper()
    while time.monotonic() < deadline:
        poll_count += 1
        latest_status_payload = _json_request(f"{base}/v1/jobs/async/job/{job_id}", headers=headers, timeout=6.0)
        final_status = str(latest_status_payload.get("status") or "").upper()
        if final_status in {"SUCCESS", "FAILURE", "INTERRUPTED"}:
            break
        time.sleep(max(float(poll_interval_seconds), 0.2))
    timed_out = final_status not in {"SUCCESS", "FAILURE", "INTERRUPTED"}
    report_payload: dict[str, Any] = {}
    state_payload: dict[str, Any] = {}
    if not timed_out and final_status == "SUCCESS":
        try:
            report_payload = _json_request(f"{base}/v1/jobs/async/job/{job_id}/report", headers=headers, timeout=8.0)
        except Exception:
            report_payload = {}
        try:
            state_payload = _json_request(f"{base}/v1/jobs/async/job/{job_id}/state", headers=headers, timeout=8.0)
        except Exception:
            state_payload = {}
    report_text = str(report_payload.get("report") or "").strip() if isinstance(report_payload, dict) else ""
    artifacts = state_payload.get("artifacts") if isinstance(state_payload, dict) else {}
    sources = artifacts.get("sources") if isinstance(artifacts, dict) else {}
    cited_urls = _string_list(list(sources.get("cited_urls") or [])) if isinstance(sources, dict) else []
    found_urls = _string_list(list(sources.get("found_urls") or [])) if isinstance(sources, dict) else []
    tools = list(artifacts.get("tools") or []) if isinstance(artifacts, dict) else []
    summary = (
        f"AI-Q research job {job_id} completed successfully through agent `{agent_type}`."
        if final_status == "SUCCESS"
        else f"AI-Q research job {job_id} ended with status `{final_status or 'UNKNOWN'}`."
    )
    if timed_out:
        summary = f"AI-Q research job {job_id} did not finish before the Mission Control polling timeout."
    return {
        "endpoint": base,
        "agent_type": agent_type,
        "job_id": job_id,
        "status": final_status or "UNKNOWN",
        "timed_out": timed_out,
        "poll_count": poll_count,
        "summary": summary,
        "report": report_text,
        "source_summary": {
            "found": int(sources.get("found") or 0) if isinstance(sources, dict) else 0,
            "cited": int(sources.get("cited") or 0) if isinstance(sources, dict) else 0,
            "cited_urls": cited_urls[:12],
            "found_urls": found_urls[:12],
        },
        "tool_count": len(tools),
        "tools": [
            {
                "name": tool.get("name"),
                "status": tool.get("status"),
                "workflow": tool.get("workflow"),
            }
            for tool in tools[:12]
            if isinstance(tool, dict)
        ],
        "status_payload": latest_status_payload,
    }


def _prometheus_query(base_url: str, query: str) -> float | None:
    encoded_query = quote_plus(query)
    payload = _json_request(f"{base_url}/api/v1/query?query={encoded_query}", timeout=6.0)
    if str(payload.get("status") or "").lower() != "success":
        return None
    data = payload.get("data")
    if not isinstance(data, dict):
        return None
    result = data.get("result")
    if not isinstance(result, list) or not result:
        return None
    first = result[0]
    if not isinstance(first, dict):
        return None
    value = first.get("value")
    if not isinstance(value, list) or len(value) < 2:
        return None
    try:
        return float(value[1])
    except (TypeError, ValueError):
        return None


def detect_nvidia_gpu_diagnostics(prometheus_url: str | None = None) -> dict[str, Any]:
    configured_url = prometheus_url or _env_first("MISSION_CONTROL_NVIDIA_PROMETHEUS_URL", "NVIDIA_PROMETHEUS_URL")
    if not configured_url:
        return {
            "available": False,
            "status": "missing",
            "summary": "No Prometheus endpoint is configured for NVIDIA GPU diagnostics.",
            "prometheus_url": None,
            "metrics": {},
            "alerts": [],
            "recommended_fixes": [
                "Configure MISSION_CONTROL_NVIDIA_PROMETHEUS_URL or NVIDIA_PROMETHEUS_URL to a Prometheus instance that scrapes dcgm-exporter metrics."
            ],
            "queries": {},
        }
    base = configured_url.rstrip("/")
    queries = {
        "average_gpu_util_percent": "avg(DCGM_FI_DEV_GPU_UTIL)",
        "framebuffer_used_mib": "sum(DCGM_FI_DEV_FB_USED)",
        "framebuffer_free_mib": "sum(DCGM_FI_DEV_FB_FREE)",
        "gpu_count": "count(DCGM_FI_DEV_GPU_UTIL)",
        "pending_pod_count": 'sum(kube_pod_status_phase{phase="Pending"})',
        "running_pod_count": 'sum(kube_pod_status_phase{phase="Running"})',
    }
    metrics: dict[str, float | None] = {}
    try:
        for key, query in queries.items():
            metrics[key] = _prometheus_query(base, query)
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError, RuntimeError):
        return {
            "available": False,
            "status": "unreachable",
            "summary": f"Configured Prometheus endpoint is not reachable at {base}.",
            "prometheus_url": base,
            "metrics": {},
            "alerts": ["Prometheus endpoint is unreachable."],
            "recommended_fixes": [
                "Verify the Prometheus URL and ensure dcgm-exporter and kube-state-metrics are being scraped."
            ],
            "queries": queries,
        }
    framebuffer_used = metrics.get("framebuffer_used_mib")
    framebuffer_free = metrics.get("framebuffer_free_mib")
    memory_utilization_percent: float | None = None
    if framebuffer_used is not None and framebuffer_free is not None and (framebuffer_used + framebuffer_free) > 0:
        memory_utilization_percent = (framebuffer_used / (framebuffer_used + framebuffer_free)) * 100.0
    metrics["memory_utilization_percent"] = memory_utilization_percent
    alerts: list[str] = []
    recommended_fixes: list[str] = []
    if metrics.get("gpu_count") in {None, 0.0}:
        alerts.append("No DCGM GPU metrics were returned from Prometheus.")
        recommended_fixes.append("Confirm dcgm-exporter is deployed and scraped by Prometheus.")
    if metrics.get("average_gpu_util_percent") is not None and float(metrics["average_gpu_util_percent"] or 0.0) > 90.0:
        alerts.append("Average GPU utilization is above 90%.")
        recommended_fixes.append("Consider reducing concurrent agent load or scaling GPU capacity before blaming the code path.")
    if memory_utilization_percent is not None and memory_utilization_percent > 90.0:
        alerts.append("Aggregate GPU framebuffer utilization is above 90%.")
        recommended_fixes.append("Reduce model size, decrease parallel workers, or increase available GPU memory.")
    pending_pods = metrics.get("pending_pod_count")
    if pending_pods is not None and pending_pods > 0:
        alerts.append(f"{int(pending_pods)} Kubernetes pods are pending.")
        recommended_fixes.append("Check scheduler pressure, node availability, GPU requests, and topology constraints.")
    status = "ready"
    if alerts:
        status = "warning"
    if metrics.get("gpu_count") in {None, 0.0}:
        status = "degraded"
    summary = "NVIDIA GPU telemetry looks healthy enough for Mission Control load."
    if status == "warning":
        summary = "NVIDIA GPU telemetry is reachable, but it shows pressure that may affect Mission Control runs."
    elif status == "degraded":
        summary = "Prometheus is reachable, but the expected NVIDIA GPU metrics are incomplete or missing."
    return {
        "available": True,
        "status": status,
        "summary": summary,
        "prometheus_url": base,
        "metrics": metrics,
        "alerts": alerts,
        "recommended_fixes": _string_list(recommended_fixes),
        "queries": queries,
    }


def detect_project_nvidia_gpu_diagnostics(
    workspace_path: str | Path,
    *,
    prometheus_url: str | None = None,
    failure_signals: list[str] | None = None,
) -> dict[str, Any]:
    telemetry = detect_nvidia_gpu_diagnostics(prometheus_url)
    workspace_health = summarize_gpu_cluster_health(workspace_path, failure_signals=failure_signals)
    workspace_relevant = bool(workspace_health.get("relevant"))
    workspace_status = str(workspace_health.get("status") or ("missing" if not workspace_relevant else "unknown"))
    telemetry_status = str(telemetry.get("status") or ("ready" if telemetry.get("available") else "missing"))

    available = bool(telemetry.get("available")) or workspace_relevant
    if workspace_relevant:
        if workspace_status == "degraded" or telemetry_status == "degraded":
            status = "degraded"
        elif telemetry_status == "warning":
            status = "warning"
        elif workspace_status == "unknown":
            status = telemetry_status if telemetry_status not in {"missing", "unreachable"} else "unknown"
        else:
            status = "ready"
    else:
        status = telemetry_status

    summary_parts: list[str] = []
    if workspace_relevant and workspace_status in {"degraded", "unknown"}:
        summary_parts.append(str(workspace_health.get("summary") or "Workspace GPU summary is incomplete."))
    elif telemetry_status in {"warning", "degraded", "unreachable"}:
        summary_parts.append(str(telemetry.get("summary") or "GPU telemetry reported an issue."))
    elif workspace_relevant:
        summary_parts.append(str(workspace_health.get("summary") or "Workspace GPU summary looks healthy."))
    else:
        summary_parts.append(str(telemetry.get("summary") or "GPU diagnostics status is unknown."))
    if telemetry_status == "warning" and workspace_relevant and workspace_status == "ready":
        telemetry_summary = str(telemetry.get("summary") or "").strip()
        if telemetry_summary and telemetry_summary not in summary_parts:
            summary_parts.append(telemetry_summary)
    summary = " ".join(part for part in summary_parts if part).strip()

    metrics = dict(telemetry.get("metrics") or {})
    pending_pod_count = workspace_health.get("pending_pod_count")
    if pending_pod_count is None and metrics.get("pending_pod_count") is not None:
        try:
            pending_pod_count = int(float(metrics["pending_pod_count"]))
        except (TypeError, ValueError):
            pending_pod_count = None
    workspace_gpu_memory_pct = workspace_health.get("gpu_memory_saturation_pct")
    telemetry_gpu_memory_pct = None
    if metrics.get("memory_utilization_percent") is not None:
        try:
            telemetry_gpu_memory_pct = float(metrics["memory_utilization_percent"])
        except (TypeError, ValueError):
            telemetry_gpu_memory_pct = None
    gpu_memory_saturation_pct = workspace_gpu_memory_pct
    if telemetry_gpu_memory_pct is not None:
        gpu_memory_saturation_pct = (
            max(float(workspace_gpu_memory_pct), telemetry_gpu_memory_pct)
            if workspace_gpu_memory_pct is not None
            else telemetry_gpu_memory_pct
        )
    gpu_memory_saturated = bool(
        workspace_health.get("gpu_memory_saturated")
        or (gpu_memory_saturation_pct is not None and gpu_memory_saturation_pct >= 90.0)
    )
    likely_failure_source = str(workspace_health.get("likely_failure_source") or "unknown")
    if likely_failure_source == "unknown" and telemetry_status in {"warning", "degraded"}:
        likely_failure_source = "infrastructure"

    observability_sources = list(workspace_health.get("observability_sources") or [])
    if telemetry.get("available") or telemetry.get("prometheus_url"):
        observability_sources = _string_list([*observability_sources, "Prometheus", "DCGM"])

    blocking_reasons = _string_list(
        [
            *[str(item) for item in list(workspace_health.get("blocking_reasons") or [])],
            *[str(item) for item in list(telemetry.get("alerts") or [])],
        ]
    )
    recommended_fixes = _string_list(
        [
            *[str(item) for item in list(telemetry.get("recommended_fixes") or [])],
            *[str(item) for item in list(workspace_health.get("recommended_fixes") or [])],
        ]
    )
    safe_commands = _string_list([str(item) for item in list(workspace_health.get("safe_commands") or [])])

    cluster_usable = workspace_health.get("cluster_usable")
    if cluster_usable is None and telemetry_status in {"ready", "warning", "degraded"}:
        cluster_usable = telemetry_status == "ready"

    return {
        **telemetry,
        "available": available,
        "status": status,
        "summary": summary or str(telemetry.get("summary") or "GPU diagnostics status is unknown."),
        "workspace_relevant": workspace_relevant,
        "telemetry_status": telemetry_status,
        "workspace_summary_status": workspace_status,
        "repo_mode_enabled": bool(workspace_health.get("repo_mode_enabled")),
        "repo_mode": workspace_health.get("repo_mode"),
        "cluster_usable": cluster_usable,
        "pending_pod_count": pending_pod_count,
        "gpu_memory_saturation_pct": gpu_memory_saturation_pct,
        "gpu_memory_saturated": gpu_memory_saturated,
        "likely_failure_source": likely_failure_source,
        "blocking_reasons": blocking_reasons,
        "detected_signals": _string_list([str(item) for item in list(workspace_health.get("detected_signals") or [])]),
        "observability_sources": observability_sources,
        "summary_files": [str(item) for item in list(workspace_health.get("summary_files") or [])],
        "safe_commands": safe_commands,
        "recommended_fixes": recommended_fixes,
    }


def detect_nvidia_local_runtime_status(workspace_path: str | Path) -> dict[str, Any]:
    root = Path(workspace_path)
    repo_mode = detect_cuda_repo_mode(root)
    tool_paths = {
        "nvidia_smi": shutil.which("nvidia-smi"),
        "nvcc": shutil.which("nvcc"),
        "nsys": shutil.which("nsys"),
        "ncu": shutil.which("ncu"),
        "compute_sanitizer": shutil.which("compute-sanitizer"),
        "cuda_gdb": shutil.which("cuda-gdb"),
        "nvidia_ctk": shutil.which("nvidia-ctk"),
        "ngc": shutil.which("ngc"),
        "docker": shutil.which("docker"),
    }
    detected_tools = [tool for tool, path in tool_paths.items() if path]
    gpu_names: list[str] = []
    driver_version: str | None = None
    cuda_release: str | None = None
    nvcc_version_text: str | None = None
    if tool_paths["nvidia_smi"]:
        code, output = _run_command(
            [
                tool_paths["nvidia_smi"],
                "--query-gpu=name,driver_version,memory.total",
                "--format=csv,noheader",
            ]
        )
        if code == 0 and output:
            gpu_names, driver_version = _parse_nvidia_smi_csv(output)
        elif output:
            driver_version = _extract_driver_version(output)
    if tool_paths["nvcc"]:
        code, output = _run_command([tool_paths["nvcc"], "--version"])
        if code == 0 and output:
            nvcc_version_text = output.strip()
            cuda_release = _extract_nvcc_release(output)

    repo_mode_enabled = bool(repo_mode.get("enabled"))
    required_tools = ["nvidia_smi", "nvcc"] if repo_mode_enabled else ["nvidia_smi"]
    optional_tools = ["nsys", "ncu", "compute_sanitizer", "cuda_gdb", "nvidia_ctk", "ngc", "docker"]
    missing_required = [tool for tool in required_tools if not tool_paths.get(tool)]
    missing_optional = [tool for tool in optional_tools if not tool_paths.get(tool)]

    profiling_ready = bool(tool_paths["nsys"] or tool_paths["ncu"])
    sanitizer_ready = bool(tool_paths["compute_sanitizer"])
    container_toolkit_ready = bool(tool_paths["docker"] and tool_paths["nvidia_ctk"])
    if repo_mode_enabled and not missing_required and profiling_ready and sanitizer_ready:
        status = "ready"
    elif repo_mode_enabled and not missing_required:
        status = "partial"
    elif repo_mode_enabled:
        status = "missing"
    elif tool_paths["nvidia_smi"]:
        status = "ready"
    elif detected_tools:
        status = "partial"
    else:
        status = "missing"

    available = bool(detected_tools) or repo_mode_enabled
    if repo_mode_enabled and status == "ready":
        summary = "CUDA repo signals and the local NVIDIA runtime toolchain are both ready for Mission Control GPU validation."
    elif repo_mode_enabled and status == "partial":
        summary = "CUDA repo signals are present, but the local NVIDIA runtime is only partially ready for full validation and profiling."
    elif repo_mode_enabled:
        summary = "CUDA repo signals are present, but the local NVIDIA runtime toolchain is missing the basics Mission Control needs."
    elif tool_paths["nvidia_smi"]:
        summary = "A local NVIDIA runtime is detectable even though this workspace does not currently look like a CUDA repo."
    else:
        summary = "No local NVIDIA runtime tools were detected."

    recommended_fixes: list[str] = []
    if repo_mode_enabled and not tool_paths["nvcc"]:
        recommended_fixes.append("Install the CUDA toolkit so Mission Control can build or validate CUDA code paths with nvcc.")
    if repo_mode_enabled and not tool_paths["nvidia_smi"]:
        recommended_fixes.append("Install or expose the NVIDIA driver tooling so Mission Control can verify GPU presence with nvidia-smi.")
    if repo_mode_enabled and not profiling_ready:
        recommended_fixes.append("Install Nsight Systems or Nsight Compute if you want evidence-backed GPU performance profiling instead of vibes.")
    if repo_mode_enabled and not sanitizer_ready:
        recommended_fixes.append("Install Compute Sanitizer if you want Mission Control to catch CUDA memory, sync, and race bugs before they become folklore.")
    if repo_mode_enabled and tool_paths["docker"] and not tool_paths["nvidia_ctk"]:
        recommended_fixes.append("Install NVIDIA Container Toolkit if your CUDA validation path depends on Dockerized GPU workloads.")
    if repo_mode_enabled and tool_paths["docker"] and tool_paths["nvidia_ctk"] and not tool_paths["ngc"]:
        recommended_fixes.append("Install the NGC CLI if you want Mission Control to pull or validate NVIDIA container smoke images directly.")
    if repo_mode_enabled and profiling_ready and not tool_paths["cuda_gdb"]:
        recommended_fixes.append("Install CUDA-GDB if you want headless GPU crash debugging instead of hoping profiler traces explain everything.")

    validation_hints = _string_list(
        [
            *[str(item) for item in list(repo_mode.get("build_commands") or [])],
            *[str(item) for item in list(repo_mode.get("test_commands") or [])],
            *[str(item) for item in list(repo_mode.get("benchmark_commands") or [])],
            *[str(item) for item in list(repo_mode.get("profile_commands") or [])],
        ]
    )
    notes = [
        "This surface checks local CUDA-adjacent runtime tools, not remote cluster telemetry.",
        "Use it with NVIDIA GPU diagnostics so Mission Control can separate local toolchain gaps from cluster pressure.",
    ]
    return {
        "available": available,
        "status": status,
        "summary": summary,
        "repo_mode_enabled": repo_mode_enabled,
        "repo_mode": repo_mode.get("mode"),
        "detected_tools": detected_tools,
        "missing_required_tools": missing_required,
        "missing_optional_tools": missing_optional,
        "tool_paths": {key: value for key, value in tool_paths.items() if value},
        "gpu_names": gpu_names,
        "driver_version": driver_version,
        "nvcc_version": nvcc_version_text,
        "cuda_release": cuda_release,
        "cuda_home": _env_first("CUDA_HOME", "CUDA_PATH"),
        "compute_sanitizer_available": sanitizer_ready,
        "nsight_systems_available": bool(tool_paths["nsys"]),
        "nsight_compute_available": bool(tool_paths["ncu"]),
        "cuda_gdb_available": bool(tool_paths["cuda_gdb"]),
        "container_toolkit_available": bool(tool_paths["nvidia_ctk"]),
        "ngc_cli_available": bool(tool_paths["ngc"]),
        "container_runtime_ready": container_toolkit_ready,
        "docker_available": bool(tool_paths["docker"]),
        "recommended_fixes": _string_list(recommended_fixes),
        "validation_hints": validation_hints[:12],
        "notes": notes,
    }


def _first_validation_command(repo_mode: dict[str, Any]) -> str | None:
    for key in ("test_commands", "benchmark_commands", "build_commands"):
        commands = [str(item).strip() for item in list(repo_mode.get(key) or []) if str(item).strip()]
        if commands:
            return commands[0]
    return None


def build_nvidia_validation_plan(workspace_path: str | Path) -> dict[str, Any]:
    root = Path(workspace_path)
    repo_mode = detect_cuda_repo_mode(root)
    local_runtime = detect_nvidia_local_runtime_status(root)
    gpu_diagnostics = detect_project_nvidia_gpu_diagnostics(root)
    primary_validation_command = _first_validation_command(repo_mode)
    configured_ngc_smoke_image = _env_first("MISSION_CONTROL_NVIDIA_NGC_SMOKE_IMAGE", "NVIDIA_NGC_SMOKE_IMAGE")

    steps: list[dict[str, Any]] = []
    if local_runtime.get("tool_paths", {}).get("nvidia_smi"):
        steps.append(
            {
                "title": "Verify local GPU visibility",
                "command": "nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader",
                "type": "smoke",
                "source": "local_runtime",
                "status": "pending",
            }
        )
    if local_runtime.get("tool_paths", {}).get("nvcc"):
        steps.append(
            {
                "title": "Verify local CUDA compiler",
                "command": "nvcc --version",
                "type": "smoke",
                "source": "local_runtime",
                "status": "pending",
            }
        )
    for command in list(repo_mode.get("build_commands") or []):
        steps.append({"title": "Build GPU code path", "command": command, "type": "build", "source": "repo_mode", "status": "pending"})
    for command in list(repo_mode.get("test_commands") or []):
        steps.append({"title": "Run GPU-targeted tests", "command": command, "type": "test", "source": "repo_mode", "status": "pending"})
    for command in list(repo_mode.get("benchmark_commands") or []):
        steps.append({"title": "Run GPU benchmarks", "command": command, "type": "benchmark", "source": "repo_mode", "status": "pending"})
    for command in list(repo_mode.get("profile_commands") or []):
        steps.append({"title": "Capture GPU profile evidence", "command": command, "type": "profile", "source": "repo_mode", "status": "pending"})
    if local_runtime.get("compute_sanitizer_available") and primary_validation_command:
        for tool_name in ("memcheck", "racecheck", "initcheck", "synccheck"):
            steps.append(
                {
                    "title": f"Run Compute Sanitizer {tool_name}",
                    "command": f"compute-sanitizer --tool {tool_name} {primary_validation_command}",
                    "type": "sanitizer",
                    "source": "local_runtime",
                    "status": "pending",
                }
            )
    if local_runtime.get("cuda_gdb_available") and primary_validation_command:
        steps.append(
            {
                "title": "Capture CUDA-GDB backtrace",
                "command": f"cuda-gdb --batch --ex run --ex bt --args {primary_validation_command}",
                "type": "debug",
                "source": "local_runtime",
                "status": "pending",
            }
        )
    if local_runtime.get("container_runtime_ready") and configured_ngc_smoke_image:
        steps.append(
            {
                "title": "Run NGC GPU container smoke",
                "command": f"docker run --rm --gpus all {configured_ngc_smoke_image} nvidia-smi",
                "type": "container_smoke",
                "source": "local_runtime",
                "status": "pending",
            }
        )

    blockers = _string_list(
        [
            *[
                f"Missing required local runtime tool: {tool}."
                for tool in list(local_runtime.get("missing_required_tools") or [])
            ],
            *[
                str(item)
                for item in list(gpu_diagnostics.get("blocking_reasons") or [])
            ],
        ]
    )
    recommended_fixes = _string_list(
        [
            *[str(item) for item in list(local_runtime.get("recommended_fixes") or [])],
            *[str(item) for item in list(gpu_diagnostics.get("recommended_fixes") or [])],
        ]
    )
    if repo_mode.get("enabled") and local_runtime.get("container_runtime_ready") and not configured_ngc_smoke_image:
        recommended_fixes.append("Set MISSION_CONTROL_NVIDIA_NGC_SMOKE_IMAGE if you want a reproducible containerized GPU smoke lane instead of trusting the host runtime.")
    evidence_targets = _string_list(
        [
            "Capture local GPU visibility and compiler versions before editing CUDA-heavy code.",
            "Record build, test, benchmark, and profile results in the handoff instead of narrating success.",
            "Record Compute Sanitizer and CUDA-GDB output when kernel behavior is suspect instead of treating crashes like folklore.",
            "Keep containerized GPU smoke output when you validate against NGC images so host drift stops masquerading as code regression.",
            *[
                str(item)
                for item in list(repo_mode.get("autotune_notes") or [])
            ],
        ]
    )

    if not repo_mode.get("enabled"):
        status = "not_applicable"
        summary = "This workspace does not currently look like a CUDA repo, so Mission Control has no NVIDIA validation plan to enforce."
    elif blockers:
        status = "blocked"
        summary = "Mission Control found NVIDIA validation blockers that should be cleared before trusting CUDA test results."
    elif str(local_runtime.get("status")) == "partial" or str(gpu_diagnostics.get("status")) in {"warning", "unknown"}:
        status = "needs_review"
        summary = "The NVIDIA validation path is usable, but it still has gaps that make results less trustworthy than they should be."
    else:
        status = "ready"
        summary = "Mission Control has a credible NVIDIA validation plan for this workspace."

    return {
        "available": bool(repo_mode.get("enabled") or local_runtime.get("available") or gpu_diagnostics.get("available")),
        "status": status,
        "summary": summary,
        "repo_mode_enabled": bool(repo_mode.get("enabled")),
        "repo_mode": repo_mode.get("mode"),
        "local_runtime_status": local_runtime.get("status"),
        "gpu_diagnostics_status": gpu_diagnostics.get("status"),
        "sanitizer_ready": bool(local_runtime.get("compute_sanitizer_available")),
        "profiler_ready": bool(local_runtime.get("nsight_systems_available") or local_runtime.get("nsight_compute_available")),
        "container_smoke_ready": bool(local_runtime.get("container_runtime_ready") and configured_ngc_smoke_image),
        "ngc_smoke_image": configured_ngc_smoke_image,
        "steps": steps[:16],
        "blockers": blockers,
        "recommended_fixes": recommended_fixes[:12],
        "evidence_targets": evidence_targets[:12],
    }
