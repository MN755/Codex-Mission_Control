---
name: mission-control-nvidia-research
description: Use Mission Control with NVIDIA AI-Q, NVIDIA Dynamo, and GPU diagnostics for deeper research and GPU-backed coding workflows.
---

# Mission Control NVIDIA Research

## Purpose

Use Mission Control to route deep technical research, GPU-backed coding capacity checks, and infrastructure diagnostics through NVIDIA-aligned runtime surfaces instead of making the chat agent guess.

The Codex chat agent is not the Mission Control Manager. It is the bridge between the user and the Mission Control Manager.

## Use when

- The user wants cited technical research before coding.
- The project may use NVIDIA Dynamo for worker inference.
- The user needs GPU-cluster or Prometheus/DCGM diagnostics before running bigger coding swarms.

## Workflow

1. Check NVIDIA Dynamo readiness if the task may use GPU-backed worker inference.
2. Check NVIDIA AI-Q readiness before delegating deeper research.
3. Use AI-Q for focused research questions that benefit from citations, data sources, and async job execution.
4. Check NVIDIA GPU diagnostics before blaming runtime failures on the codebase.
5. Bring the research result back into Mission Control planning or implementation with a compact evidence-based summary.

## Mission Control calls

Tools:
- `mission_control_get_nvidia_dynamo_status`
- `mission_control_get_nvidia_aiq_status`
- `mission_control_run_nvidia_aiq_research`
- `mission_control_get_nvidia_gpu_diagnostics`

Resources:
- `mission-control://projects/{project_id}/nvidia-dynamo`
- `mission-control://projects/{project_id}/nvidia-aiq`
- `mission-control://projects/{project_id}/nvidia-gpu-diagnostics`
- `mission-control://projects/{project_id}/diagnostics`

## User-facing output

- State clearly whether Dynamo, AI-Q, and GPU diagnostics are actually available.
- If AI-Q research ran, summarize the answer, cited-source posture, and any infrastructure limitations.
- If GPU telemetry shows pressure, say that explicitly before recommending larger swarms or heavier models.

## Never do

- Do not claim NVIDIA infrastructure is configured if the probes say otherwise.
- Do not hide missing endpoints, auth, or Prometheus gaps.
- Do not blur “research completed” with “code changed.”

## Example invocation

`Use Mission Control and NVIDIA AI-Q to research the best approach for integrating a CUDA-backed service into this repo.`
