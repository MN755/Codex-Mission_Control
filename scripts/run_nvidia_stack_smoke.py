from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SERVER_SRC = REPO_ROOT / "apps" / "server" / "src"
if str(SERVER_SRC) not in sys.path:
    sys.path.insert(0, str(SERVER_SRC))

from gpu_support import detect_cuda_repo_mode
from nvidia_devstack import MockNvidiaStackConfig, start_mock_nvidia_stack
from nvidia_support import (
    DEFAULT_NVIDIA_SMOKE_QUERY,
    build_nvidia_validation_plan,
    detect_nvidia_aiq_status,
    detect_nvidia_dynamo_status,
    detect_nvidia_nim_status,
    detect_nvidia_local_runtime_status,
    detect_project_nvidia_gpu_diagnostics,
    run_nvidia_aiq_research,
)


def _workspace_for_smoke(root: Path) -> Path:
    workspace = Path(tempfile.mkdtemp(prefix="mission-control-nvidia-smoke-")).resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "CMakeLists.txt").write_text(
        "cmake_minimum_required(VERSION 3.28)\nproject(cuda_smoke LANGUAGES CXX CUDA)\nfind_package(CUDAToolkit REQUIRED)\n",
        encoding="utf-8",
    )
    kernels = workspace / "kernels"
    kernels.mkdir(parents=True, exist_ok=True)
    (kernels / "main.cu").write_text("__global__ void smoke_kernel() {}\n", encoding="utf-8")
    obs = workspace / ".mission-control" / "gpu"
    obs.mkdir(parents=True, exist_ok=True)
    (obs / "prometheus-summary.json").write_text(
        json.dumps({"source": "prometheus", "pending_pods": 0, "gpu_memory_utilization": 42}, indent=2),
        encoding="utf-8",
    )
    return workspace


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a Mission Control NVIDIA stack smoke test.")
    parser.add_argument("--workspace", type=Path, default=None, help="Workspace path to inspect. Defaults to a generated mock CUDA workspace.")
    parser.add_argument("--mock-stack", action="store_true", help="Start local fake Dynamo, AI-Q, and Prometheus endpoints for contract testing.")
    parser.add_argument("--dynamo-endpoint", type=str, default=None)
    parser.add_argument("--nim-endpoint", type=str, default=None)
    parser.add_argument("--aiq-endpoint", type=str, default=None)
    parser.add_argument("--prometheus-url", type=str, default=None)
    parser.add_argument("--query", type=str, default=DEFAULT_NVIDIA_SMOKE_QUERY)
    args = parser.parse_args()

    workspace = args.workspace.resolve() if args.workspace else _workspace_for_smoke(REPO_ROOT)
    stack = None
    try:
        if args.mock_stack:
            stack = start_mock_nvidia_stack(MockNvidiaStackConfig())
            if not args.dynamo_endpoint:
                args.dynamo_endpoint = stack.dynamo_url
            if not args.nim_endpoint:
                args.nim_endpoint = stack.nim_url
            if not args.aiq_endpoint:
                args.aiq_endpoint = stack.aiq_url
            if not args.prometheus_url:
                args.prometheus_url = stack.prometheus_url
        if args.dynamo_endpoint:
            os.environ["MISSION_CONTROL_NVIDIA_DYNAMO_ENDPOINT"] = args.dynamo_endpoint
        if args.nim_endpoint:
            os.environ["MISSION_CONTROL_NVIDIA_NIM_ENDPOINT"] = args.nim_endpoint
        if args.aiq_endpoint:
            os.environ["MISSION_CONTROL_NVIDIA_AIQ_ENDPOINT"] = args.aiq_endpoint
        if args.prometheus_url:
            os.environ["MISSION_CONTROL_NVIDIA_PROMETHEUS_URL"] = args.prometheus_url

        result = {
            "workspace": workspace.as_posix(),
            "cuda_repo_mode": detect_cuda_repo_mode(workspace),
            "dynamo_status": detect_nvidia_dynamo_status(args.dynamo_endpoint),
            "nim_status": detect_nvidia_nim_status(args.nim_endpoint),
            "aiq_status": detect_nvidia_aiq_status(args.aiq_endpoint),
            "gpu_diagnostics": detect_project_nvidia_gpu_diagnostics(workspace, prometheus_url=args.prometheus_url),
            "local_runtime": detect_nvidia_local_runtime_status(workspace),
            "validation_plan": build_nvidia_validation_plan(workspace),
        }
        if args.aiq_endpoint:
            result["aiq_research"] = run_nvidia_aiq_research(
                query=args.query,
                endpoint=args.aiq_endpoint,
                timeout_seconds=15,
                poll_interval_seconds=0.1,
            )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    finally:
        if stack is not None:
            stack.close()


if __name__ == "__main__":
    raise SystemExit(main())
