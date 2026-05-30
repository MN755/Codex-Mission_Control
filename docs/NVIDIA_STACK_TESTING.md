# NVIDIA Stack Testing

Mission Control now has two NVIDIA testing lanes:

## 1. Mock stack smoke test

This starts local fake NVIDIA Dynamo, NIM, AI-Q, and Prometheus endpoints and then exercises the real Mission Control HTTP detectors against them.

```powershell
python scripts/run_nvidia_stack_smoke.py --mock-stack
```

Use this when you want to verify the integration contract without needing a real GPU cluster or real NVIDIA services.

## 2. Real endpoint smoke test

Point the same script at real infrastructure when it exists:

```powershell
python scripts/run_nvidia_stack_smoke.py `
  --workspace C:\path\to\cuda-repo `
  --dynamo-endpoint http://your-dynamo:8000 `
  --nim-endpoint https://integrate.api.nvidia.com `
  --aiq-endpoint http://your-aiq:8000 `
  --prometheus-url http://your-prometheus:9090
```

What it checks:

- CUDA repo detection
- NVIDIA Dynamo frontend reachability and models
- NVIDIA NIM reachability and models
- NVIDIA AI-Q health, agents, data sources, and async research flow
- merged GPU diagnostics
- local NVIDIA runtime posture, including Compute Sanitizer, Nsight, CUDA-GDB, and container-runtime readiness
- generated NVIDIA validation plan

## Why this exists

Because "we added support" is not the same thing as "the contracts actually work."
