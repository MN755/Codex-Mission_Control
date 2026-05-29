from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any


CUDA_FILE_EXTENSIONS = {".cu", ".cuh", ".ptx", ".cubin"}
CPP_FILE_EXTENSIONS = {".cc", ".cpp", ".cxx", ".hpp", ".hxx"}
MAX_SCANNED_FILES = 1500
MAX_SUMMARY_BYTES = 200_000
OBSERVABILITY_DIR_CANDIDATES = [
    ".mission-control/gpu",
    "mission-control/gpu",
    "observability/gpu",
    "diagnostics/gpu",
    "gpu-observability",
]
OBSERVABILITY_FILE_HINTS = ("gpu", "dcgm", "grafana", "prometheus", "nvidia", "cluster-health")
OBSERVABILITY_FILE_EXTENSIONS = {".json", ".jsonl", ".ndjson", ".yaml", ".yml", ".txt", ".log", ".out"}
INFRA_PATTERNS: list[tuple[str, str]] = [
    (r"insufficient\s+nvidia\.com/gpu", "Kubernetes cannot currently schedule the requested GPUs."),
    (r"unschedulable", "GPU workloads are unschedulable right now."),
    (r"device\s+plugin", "The NVIDIA device plugin looks unhealthy."),
    (r"dcgm(?:-exporter)?\s+(?:down|failed|error|unreachable)", "DCGM telemetry looks unhealthy."),
    (r"prometheus\s+(?:down|failed|error|unreachable|scrape failed)", "Prometheus telemetry is degraded."),
    (r"grafana\s+(?:down|failed|error|unreachable)", "Grafana telemetry is degraded."),
    (r"\bnode\b.*\bnotready\b", "At least one GPU node is not ready."),
    (r"\bnode\b.*\bcordoned\b", "A GPU node is cordoned."),
    (r"\btaint\b.*nvidia\.com/gpu", "GPU node taints are blocking scheduling."),
    (r"\bo?omkilled\b", "A GPU workload was OOM-killed by the platform."),
    (r"\bxid\b", "The GPU reported an Xid hardware/runtime fault."),
    (r"driver version is insufficient", "The NVIDIA driver/runtime combination is invalid."),
]
CODE_PATTERNS: list[tuple[str, str]] = [
    (r"compilation terminated", "Compilation failed inside the codebase."),
    (r"undefined reference", "Linking failed for the current code changes."),
    (r"\bassert(?:ion)?\b", "A test or runtime assertion failed."),
    (r"illegal memory access", "A CUDA kernel likely performed an illegal memory access."),
    (r"invalid configuration argument", "A CUDA launch configuration looks invalid."),
    (r"segmentation fault", "The process crashed during execution."),
    (r"test(?:s)? failed", "The test suite reported a code-facing failure."),
]


def _scan_files(root: Path) -> list[Path]:
    return [path for path in root.rglob("*") if path.is_file()][:MAX_SCANNED_FILES]


def _safe_read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def _first_existing(root: Path, candidates: list[str]) -> list[Path]:
    hits: list[Path] = []
    for candidate in candidates:
        path = root / candidate
        if path.exists():
            hits.append(path)
    return hits


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        text = str(item).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        ordered.append(text)
    return ordered


def _candidate_observability_files(root: Path) -> list[Path]:
    candidates: list[Path] = []
    for directory in _first_existing(root, OBSERVABILITY_DIR_CANDIDATES):
        if directory.is_file():
            candidates.append(directory)
            continue
        for child in directory.rglob("*"):
            if child.is_file():
                candidates.append(child)
    for path in _scan_files(root):
        lowered = path.name.lower()
        if path.suffix.lower() not in OBSERVABILITY_FILE_EXTENSIONS:
            continue
        if any(token in lowered for token in OBSERVABILITY_FILE_HINTS):
            candidates.append(path)
    env_paths = os.environ.get("MISSION_CONTROL_GPU_SUMMARY_PATHS", "")
    for raw_path in re.split(r"[;,]", env_paths):
        text = raw_path.strip()
        if not text:
            continue
        path = Path(text).expanduser()
        if path.exists() and path.is_file():
            candidates.append(path)
    ordered = sorted({path.resolve() for path in candidates if path.exists() and path.is_file()}, key=str)
    return ordered[:12]


def _source_labels(path: Path, text: str) -> list[str]:
    haystack = f"{path.name.lower()}\n{text.lower()}"
    labels: list[str] = []
    if "prometheus" in haystack:
        labels.append("Prometheus")
    if "dcgm" in haystack or "nvidia-smi" in haystack:
        labels.append("DCGM")
    if "grafana" in haystack:
        labels.append("Grafana")
    if not labels:
        labels.append("GPU summary")
    return labels


def _extract_count(text: str, patterns: list[str]) -> int | None:
    lowered = text.lower()
    for pattern in patterns:
        match = re.search(pattern, lowered)
        if match:
            try:
                return int(float(match.group(1)))
            except (TypeError, ValueError):
                continue
    return None


def _extract_percent(text: str, patterns: list[str]) -> float | None:
    lowered = text.lower()
    for pattern in patterns:
        match = re.search(pattern, lowered)
        if not match:
            continue
        try:
            value = float(match.group(1))
        except (TypeError, ValueError):
            continue
        return value * 100.0 if 0.0 <= value <= 1.0 else value
    return None


def _append_unique(target: list[str], values: list[str]) -> None:
    for value in values:
        if value not in target:
            target.append(value)


def detect_cuda_repo_mode(workspace_path: str | Path) -> dict[str, Any]:
    root = Path(workspace_path)
    if not root.exists() or not root.is_dir():
        return {
            "enabled": False,
            "mode": None,
            "signals": [],
            "languages": [],
            "frameworks": [],
            "build_commands": [],
            "test_commands": [],
            "profile_commands": [],
            "benchmark_commands": [],
            "autotune_notes": [],
            "important_paths": [],
        }

    files = _scan_files(root)
    relative_paths = [path.relative_to(root).as_posix() for path in files]
    languages: list[str] = []
    frameworks: list[str] = []
    build_commands: list[str] = []
    test_commands: list[str] = []
    profile_commands: list[str] = []
    benchmark_commands: list[str] = []
    signals: list[str] = []
    important_paths: list[str] = []
    autotune_notes: list[str] = []

    if any(path.suffix.lower() in CPP_FILE_EXTENSIONS for path in files):
        languages.append("C++")
    if any(path.suffix.lower() in CUDA_FILE_EXTENSIONS for path in files):
        _append_unique(languages, ["C++", "CUDA"])
        signals.append("Detected CUDA source files (*.cu, *.cuh, *.ptx, or *.cubin).")

    top_texts: list[str] = []
    for candidate in [
        root / "CMakeLists.txt",
        root / "Makefile",
        root / "pyproject.toml",
        root / "setup.py",
        root / "requirements.txt",
        root / "README.md",
    ]:
        if candidate.exists():
            top_texts.append(_safe_read_text(candidate))
            important_paths.append(candidate.relative_to(root).as_posix())
    combined_text = "\n".join(top_texts).lower()

    if any(token in combined_text for token in ("cuda", "cudart", "cublas", "cudnn", "nvcc")):
        if "CUDA" not in languages:
            _append_unique(languages, ["CUDA"])
        frameworks.append("NVIDIA CUDA")
        signals.append("Detected CUDA toolchain references in build or project files.")
    if any(token in combined_text for token in ("cuda::tile", "cuda tile", "tile programming", "cuda::std::")):
        frameworks.append("CUDA Tile")
        signals.append("Detected CUDA Tile programming signals.")
        autotune_notes.append("Treat tile shapes and launch configuration as tunable performance parameters, not fixed trivia.")
    if any(token in combined_text for token in ("nsight", "nsys", "ncu")):
        frameworks.append("Nsight")
        signals.append("Detected Nsight profiling tooling references.")
    if any(token in combined_text for token in ("cupy", "numba.cuda", "torch.utils.cpp_extension", "pytorch")):
        languages.append("Python")
        frameworks.append("Python GPU stack")
        signals.append("Detected Python-side GPU integration signals.")

    if (root / "CMakeLists.txt").exists() and "cuda" in combined_text:
        _append_unique(
            build_commands,
            [
                "cmake -S . -B build -DCMAKE_BUILD_TYPE=Release",
                "cmake --build build --parallel",
            ],
        )
        _append_unique(test_commands, ["ctest --test-dir build --output-on-failure"])
    elif (root / "Makefile").exists() and any(token in combined_text for token in ("nvcc", "cuda")):
        build_commands.append("make")
    if (root / "pyproject.toml").exists() or (root / "setup.py").exists():
        if any(token in combined_text for token in ("cupy", "numba", "torch.utils.cpp_extension", "cuda")):
            build_commands.append("python -m pip install -e .")
    if (root / "requirements.txt").exists() and any("pytest" in text.lower() for text in top_texts):
        test_commands.append("python -m pytest")
    if any("pytest" in path for path in relative_paths):
        _append_unique(test_commands, ["python -m pytest"])

    if any(path.startswith("benchmarks/") for path in relative_paths):
        benchmark_commands.append("ctest --test-dir build -L benchmark --output-on-failure")
        important_paths.append("benchmarks")
    elif any(token in combined_text for token in ("benchmark", "microbench")):
        benchmark_commands.append("Run the project benchmark target after kernel edits.")
    if any(path.startswith("profiles/") for path in relative_paths):
        important_paths.append("profiles")
    if any(path.startswith("kernels/") or "/kernels/" in path for path in relative_paths):
        important_paths.append("kernels")

    if build_commands or benchmark_commands:
        profile_commands.append("nsys profile --force-overwrite true --sample=none --output .runtime/diagnostics/nsys-report <gpu-command>")
        profile_commands.append("ncu --set full --target-processes all <gpu-command>")

    mode: str | None
    if "CUDA Tile" in frameworks:
        mode = "cuda_tile_cpp"
    elif "NVIDIA CUDA" in frameworks:
        mode = "cuda_cpp"
    elif "CUDA" in languages:
        mode = "cuda_cpp"
    elif "Python GPU stack" in frameworks:
        mode = "cuda_python"
    else:
        mode = None

    if mode is not None:
        autotune_notes.append("Keep a benchmark-before/after loop so kernel changes prove speedups instead of narrating them.")
        autotune_notes.append("Separate infra blockers from kernel bugs before iterating on code.")

    return {
        "enabled": mode is not None,
        "mode": mode,
        "signals": _dedupe(signals),
        "languages": _dedupe(languages),
        "frameworks": _dedupe(frameworks),
        "build_commands": _dedupe(build_commands),
        "test_commands": _dedupe(test_commands),
        "profile_commands": _dedupe(profile_commands),
        "benchmark_commands": _dedupe(benchmark_commands),
        "autotune_notes": _dedupe(autotune_notes),
        "important_paths": _dedupe(important_paths),
    }


def summarize_gpu_cluster_health(workspace_path: str | Path, *, failure_signals: list[str] | None = None) -> dict[str, Any]:
    root = Path(workspace_path)
    repo_mode = detect_cuda_repo_mode(root)
    summary_files = _candidate_observability_files(root) if root.exists() and root.is_dir() else []
    relevant = bool(repo_mode["enabled"] or summary_files)

    if not relevant:
        return {
            "relevant": False,
            "repo_mode_enabled": False,
            "repo_mode": None,
            "status": "ready",
            "summary": "No CUDA repo signals or GPU observability inputs were detected for this workspace.",
            "cluster_usable": None,
            "pending_pod_count": None,
            "gpu_memory_saturation_pct": None,
            "gpu_memory_saturated": False,
            "likely_failure_source": "unknown",
            "blocking_reasons": [],
            "detected_signals": [],
            "observability_sources": [],
            "summary_files": [],
            "recommended_fixes": [],
            "safe_commands": [],
        }

    combined_chunks: list[str] = []
    observability_sources: list[str] = []
    detected_signals: list[str] = []
    for path in summary_files:
        text = _safe_read_text(path)[:MAX_SUMMARY_BYTES]
        if path.suffix.lower() == ".json":
            try:
                parsed = json.loads(text)
                text = json.dumps(parsed, indent=2, sort_keys=True)
            except json.JSONDecodeError:
                pass
        combined_chunks.append(f"# {path.name}\n{text}")
        _append_unique(observability_sources, _source_labels(path, text))
        detected_signals.append(f"Ingested {path.name}.")
    if failure_signals:
        combined_chunks.append("\n".join(str(item) for item in failure_signals if str(item).strip()))
    combined_text = "\n".join(combined_chunks).lower()

    pending_pod_count = _extract_count(
        combined_text,
        [
            r"pending[_ -]?pods?[^0-9]*([0-9]+)",
            r"pods?[_ -]?pending[^0-9]*([0-9]+)",
            r"\bpending\b[^0-9]{0,20}([0-9]+)",
        ],
    )
    gpu_memory_pct = _extract_percent(
        combined_text,
        [
            r"gpu[_ -]?memory(?:[_ -]?(?:util(?:ization)?|saturation|used_pct))?[^0-9]*([0-9]+(?:\.[0-9]+)?)",
            r"fb[_ -]?used[_ -]?pct[^0-9]*([0-9]+(?:\.[0-9]+)?)",
            r"memory[_ -]?saturation[^0-9]*([0-9]+(?:\.[0-9]+)?)",
        ],
    )
    gpu_memory_saturated = bool(
        (gpu_memory_pct is not None and gpu_memory_pct >= 90.0)
        or any(token in combined_text for token in ("cuda out of memory", "out of memory", "memory pressure", "gpu memory exhausted"))
    )

    blocking_reasons: list[str] = []
    if pending_pod_count and pending_pod_count > 0:
        blocking_reasons.append(f"{pending_pod_count} GPU pod(s) are pending.")
    if gpu_memory_saturated:
        if gpu_memory_pct is not None:
            blocking_reasons.append(f"GPU memory saturation is about {gpu_memory_pct:.0f}%.")
        else:
            blocking_reasons.append("GPU memory looks saturated or out-of-memory failures were reported.")

    infra_hits = [message for pattern, message in INFRA_PATTERNS if re.search(pattern, combined_text)]
    code_hits = [message for pattern, message in CODE_PATTERNS if re.search(pattern, combined_text)]
    _append_unique(blocking_reasons, infra_hits)

    if infra_hits or pending_pod_count or gpu_memory_saturated:
        likely_failure_source = "infrastructure" if not code_hits else "mixed"
    elif code_hits:
        likely_failure_source = "code"
    else:
        likely_failure_source = "unknown"

    if blocking_reasons:
        status = "degraded"
        cluster_usable = False
        summary = "GPU cluster lane found infrastructure pressure that can block or invalidate CUDA runs."
    elif summary_files:
        status = "ready"
        cluster_usable = True
        summary = "GPU cluster summaries do not show pending-pod blockers or obvious memory saturation."
    else:
        status = "unknown"
        cluster_usable = None
        summary = "CUDA repo signals were detected, but no Prometheus/DCGM/Grafana-style summaries were available to judge cluster health."

    recommended_fixes: list[str] = []
    safe_commands: list[str] = []
    if status == "unknown":
        recommended_fixes.append("Provide a local Prometheus, DCGM exporter, or Grafana summary file so Mission Control can classify GPU infrastructure health.")
    if pending_pod_count and pending_pod_count > 0:
        recommended_fixes.append("Clear pending GPU pods before blaming the code path for the failed run.")
        safe_commands.append("kubectl get pods -A --field-selector=status.phase=Pending")
        safe_commands.append("kubectl describe pods -A")
    if gpu_memory_saturated:
        recommended_fixes.append("Treat the failure as GPU-capacity pressure first; reduce concurrency or free memory before changing kernels.")
        safe_commands.append("kubectl top pods -A")
        safe_commands.append("kubectl describe nodes")
    if likely_failure_source == "code":
        recommended_fixes.append("The current summaries look cluster-healthy enough that the failure is more likely in the CUDA code path.")
    elif likely_failure_source == "mixed":
        recommended_fixes.append("Both infrastructure and code-facing signals exist, so avoid declaring a clean root cause yet.")
    if summary_files:
        safe_commands.append("kubectl get events -A --sort-by=.lastTimestamp")

    return {
        "relevant": True,
        "repo_mode_enabled": bool(repo_mode["enabled"]),
        "repo_mode": repo_mode["mode"],
        "status": status,
        "summary": summary,
        "cluster_usable": cluster_usable,
        "pending_pod_count": pending_pod_count,
        "gpu_memory_saturation_pct": gpu_memory_pct,
        "gpu_memory_saturated": gpu_memory_saturated,
        "likely_failure_source": likely_failure_source,
        "blocking_reasons": _dedupe(blocking_reasons),
        "detected_signals": _dedupe([*list(repo_mode["signals"]), *detected_signals, *code_hits]),
        "observability_sources": _dedupe(observability_sources),
        "summary_files": [path.as_posix() for path in summary_files],
        "recommended_fixes": _dedupe(recommended_fixes),
        "safe_commands": _dedupe(safe_commands),
    }
