from __future__ import annotations

import platform
import shutil
from typing import Any

from config import REPO_ROOT
from nvidia_support import detect_nvidia_aiq_status, detect_nvidia_dynamo_status, detect_project_nvidia_gpu_diagnostics
from webwright_support import detect_webwright_status


TOOL_CATALOG: list[dict[str, Any]] = [
    {"id": "file-search", "name": "File Search", "category": "Core tools", "summary": "Search the local workspace quickly.", "risk_level": "low"},
    {"id": "format-changer", "name": "Format Changer", "category": "Core tools", "summary": "Rewrite or normalize code and content formatting.", "risk_level": "low"},
    {"id": "write-publishable-docs", "name": "Write Publishable Docs", "category": "Docs tools", "summary": "Generate polished public-facing documentation.", "risk_level": "low"},
    {"id": "github-wiki-creator", "name": "GitHub Wiki Creator", "category": "Docs tools", "summary": "Publish docs to a connected GitHub wiki.", "risk_level": "medium"},
    {"id": "github-deployment-creator", "name": "GitHub Deployment Creator", "category": "Deployment tools", "summary": "Create deployment-related GitHub artifacts.", "risk_level": "medium"},
    {"id": "skill-creator", "name": "Skill Creator", "category": "Core tools", "summary": "Create local Mission Control or Codex skills.", "risk_level": "medium"},
    {"id": "goal-reminder", "name": "Goal Reminder", "category": "Core tools", "summary": "Keep the current build goal visible to the manager and workers.", "risk_level": "low"},
    {"id": "security-review", "name": "Security Review", "category": "Testing tools", "summary": "Run a local security review checklist or specialist model.", "risk_level": "medium"},
    {"id": "python-workspace-with-uv", "name": "Python Workspace with uv", "category": "Core tools", "summary": "Prepare isolated Python environments and run Python repo tasks through uv when it is installed.", "risk_level": "medium"},
    {"id": "python-quality-with-ruff", "name": "Python Quality with Ruff", "category": "Testing tools", "summary": "Run Ruff lint and format checks for Python repos.", "risk_level": "low"},
    {"id": "repo-hooks-with-pre-commit", "name": "Repo Hooks with pre-commit", "category": "Testing tools", "summary": "Run repo-native hook contracts through pre-commit.", "risk_level": "medium"},
    {"id": "python-sessions-with-nox", "name": "Python Sessions with Nox", "category": "Testing tools", "summary": "Run project-defined Python sessions like tests, lint, and docs.", "risk_level": "medium"},
    {"id": "codebase-intake-with-ripgrep", "name": "Codebase Intake with ripgrep", "category": "Core tools", "summary": "Search the workspace quickly with ripgrep for intake, impact analysis, and targeted debugging.", "risk_level": "low"},
    {"id": "symbol-map-with-tree-sitter", "name": "Symbol Map with tree-sitter", "category": "Core tools", "summary": "Build parser-backed symbol maps and safer change impact hints when tree-sitter is available.", "risk_level": "medium"},
    {"id": "test-in-chromium", "name": "Test in Chromium", "category": "Testing tools", "summary": "Run browser checks in Chromium when available.", "risk_level": "low"},
    {"id": "browser-automation-with-webwright", "name": "Browser Automation with Webwright", "category": "Testing tools", "summary": "Use the local Webwright browser-agent harness for multi-step browser work when it is installed.", "risk_level": "medium"},
    {"id": "nvidia-dynamo-inference", "name": "NVIDIA Dynamo Inference", "category": "Infrastructure tools", "summary": "Route Mission Control coding workers through an NVIDIA Dynamo OpenAI-compatible frontend when available.", "risk_level": "high"},
    {"id": "nvidia-aiq-deep-research", "name": "NVIDIA AI-Q Deep Research", "category": "Search/research tools", "summary": "Delegate deep cited research to an NVIDIA AI-Q deployment when available.", "risk_level": "medium"},
    {"id": "nvidia-gpu-cluster-diagnostics", "name": "NVIDIA GPU Cluster Diagnostics", "category": "Infrastructure tools", "summary": "Inspect Prometheus and DCGM-backed GPU telemetry before blaming failing coding runs on the repo.", "risk_level": "medium"},
    {"id": "secret-scan-with-gitleaks", "name": "Secret Scan with Gitleaks", "category": "Testing tools", "summary": "Run a redacted local secret scan before handoff or release.", "risk_level": "medium"},
    {"id": "dependency-audit-with-osv-scanner", "name": "Dependency Audit with OSV-Scanner", "category": "Testing tools", "summary": "Scan repo lockfiles for known dependency vulnerabilities.", "risk_level": "medium"},
    {"id": "python-audit-with-pip-audit", "name": "Python Audit with pip-audit", "category": "Testing tools", "summary": "Audit Python dependencies for known vulnerabilities.", "risk_level": "medium"},
    {"id": "deploy-with-vercel", "name": "Deploy with Vercel", "category": "Deployment tools", "summary": "Deploy through a configured Vercel account.", "risk_level": "high"},
    {"id": "web-search-with-approval", "name": "Web Search with Approval", "category": "Search/research tools", "summary": "Use live web search with explicit approval.", "risk_level": "medium"},
    {"id": "extra-sandbox", "name": "Extra Sandbox", "category": "Experimental environments", "summary": "Use a broader or alternate local sandbox when configured.", "risk_level": "high"},
    {"id": "test-in-linux-wsl", "name": "Test in Linux / WSL", "category": "Testing tools", "summary": "Run validation in Linux or WSL when available.", "risk_level": "medium"},
    {"id": "convert-sound-to-text", "name": "Convert Sound to Text", "category": "Docs tools", "summary": "Transcribe local audio artifacts into text notes.", "risk_level": "medium"},
    {"id": "ascii-image-creator", "name": "ASCII Image Creator", "category": "Docs tools", "summary": "Produce ASCII art or terminal-friendly image previews.", "risk_level": "low"},
    {"id": "platform-creator", "name": "Platform Creator", "category": "Experimental environments", "summary": "Scaffold additional platform surfaces around the current project.", "risk_level": "high"},
    {"id": "cuda-test-environment", "name": "CUDA Test Environment", "category": "Experimental environments", "summary": "Run GPU-targeted checks when CUDA is installed.", "risk_level": "high"},
    {"id": "test-in-windows", "name": "Test in Windows", "category": "Testing tools", "summary": "Run validation flows on Windows.", "risk_level": "medium"},
    {"id": "test-in-android", "name": "Test in Android", "category": "Testing tools", "summary": "Use an Android testing environment when configured.", "risk_level": "high"},
    {"id": "test-in-macos", "name": "Test in MacOS", "category": "Testing tools", "summary": "Use local macOS-specific validation when available.", "risk_level": "high"},
    {"id": "test-in-ios", "name": "Test in iOS", "category": "Testing tools", "summary": "Use local iOS validation when available.", "risk_level": "high"},
    {"id": "test-in-safari", "name": "Test in Safari", "category": "Testing tools", "summary": "Use Safari-specific browser checks when available.", "risk_level": "medium"},
    {"id": "test-in-raspberry-pi-os", "name": "Test in Raspberry Pi OS", "category": "Testing tools", "summary": "Run validation on Raspberry Pi OS when configured.", "risk_level": "high"},
    {"id": "test-in-chromebook-os", "name": "Test in Chromebook OS", "category": "Testing tools", "summary": "Run validation against a ChromeOS-like environment when configured.", "risk_level": "high"},
]


def _is_windows() -> bool:
    return platform.system().lower().startswith("win")


def _is_macos() -> bool:
    return platform.system().lower() == "darwin"


def _is_linux() -> bool:
    return platform.system().lower() == "linux"


def _availability(tool_id: str, *, provider: str, connected_accounts: dict[str, Any]) -> tuple[str, list[str]]:
    notes: list[str] = []
    if tool_id in {"file-search", "format-changer", "write-publishable-docs", "goal-reminder", "ascii-image-creator"}:
        return "available", notes
    if tool_id == "python-workspace-with-uv":
        return ("available" if shutil.which("uv") else "needs_setup"), ["Mission Control can use uv for isolated Python sync and execution when the CLI is installed."]
    if tool_id == "python-quality-with-ruff":
        return ("available" if shutil.which("ruff") else "needs_setup"), ["Ruff gives Mission Control a fast Python lint and format gate."]
    if tool_id == "repo-hooks-with-pre-commit":
        return ("available" if shutil.which("pre-commit") else "needs_setup"), ["Use this when the repo already has a pre-commit config instead of inventing a fake hygiene contract."]
    if tool_id == "python-sessions-with-nox":
        return ("available" if shutil.which("nox") else "needs_setup"), ["Nox is useful when pytest alone is not the project's real validation entry point."]
    if tool_id == "codebase-intake-with-ripgrep":
        return ("available" if shutil.which("rg") else "needs_setup"), ["ripgrep is the preferred search backend for intake and impact analysis."]
    if tool_id == "symbol-map-with-tree-sitter":
        return ("available" if shutil.which("tree-sitter") else "needs_setup"), ["tree-sitter is optional, but it unlocks parser-backed codebase maps instead of shallow file scans."]
    if tool_id == "security-review":
        notes.append("Uses the configured security workflow when available, otherwise falls back to the normal security checklist.")
        return "available", notes
    if tool_id == "test-in-chromium":
        notes.append("Browser availability depends on local Chromium or browser tooling.")
        return "available", notes
    if tool_id == "browser-automation-with-webwright":
        status = detect_webwright_status()
        notes.append(str(status.get("summary") or "Webwright runtime status is unknown."))
        if status.get("workspace_signals"):
            notes.append("Project-specific Webwright readiness is available through the dedicated Mission Control Webwright status surface.")
        if status.get("available"):
            return "available", notes
        return ("needs_setup" if status.get("install_status") in {"missing", "partial"} else "coming_soon"), notes
    if tool_id == "nvidia-dynamo-inference":
        status = detect_nvidia_dynamo_status()
        notes.append(str(status.get("summary") or "NVIDIA Dynamo status is unknown."))
        return ("available" if status.get("reachable") else "needs_setup"), notes
    if tool_id == "nvidia-aiq-deep-research":
        status = detect_nvidia_aiq_status()
        notes.append(str(status.get("summary") or "NVIDIA AI-Q status is unknown."))
        return ("available" if status.get("available") else "needs_setup"), notes
    if tool_id == "nvidia-gpu-cluster-diagnostics":
        status = detect_project_nvidia_gpu_diagnostics(REPO_ROOT)
        notes.append(str(status.get("summary") or "NVIDIA GPU diagnostics status is unknown."))
        if status.get("available"):
            return "available", notes
        return ("needs_setup" if status.get("status") in {"missing", "unreachable", "unknown"} else "experimental"), notes
    if tool_id == "secret-scan-with-gitleaks":
        return ("available" if shutil.which("gitleaks") else "needs_setup"), ["Redacted secret scanning is the sane default gate before handoff or release."]
    if tool_id == "dependency-audit-with-osv-scanner":
        return ("available" if shutil.which("osv-scanner") else "needs_setup"), ["Use OSV-Scanner when dependency risk matters across languages."]
    if tool_id == "python-audit-with-pip-audit":
        return ("available" if shutil.which("pip-audit") else "needs_setup"), ["Use pip-audit for Python dependency vulnerability checks."]
    if tool_id in {"github-wiki-creator", "github-deployment-creator"}:
        github_status = connected_accounts.get("github", {})
        return ("available" if github_status.get("status") == "connected" else "needs_setup"), notes
    if tool_id == "deploy-with-vercel":
        vercel_status = connected_accounts.get("vercel", {})
        return ("available" if vercel_status.get("status") == "connected" else "needs_setup"), notes
    if tool_id == "web-search-with-approval":
        notes.append("Web search stays approval-gated unless the user explicitly enables it.")
        return "needs_setup", notes
    if tool_id in {"extra-sandbox", "platform-creator"}:
        return "experimental", notes
    if tool_id == "skill-creator":
        notes.append("External Codex skill discovery depends on local Codex configuration.")
        return "available", notes
    if tool_id == "test-in-linux-wsl":
        if _is_linux():
            return "available", notes
        if _is_windows():
            notes.append("WSL or another Linux runtime must be configured first.")
            return "needs_setup", notes
        return "experimental", notes
    if tool_id == "convert-sound-to-text":
        return "needs_setup", notes
    if tool_id == "cuda-test-environment":
        notes.append("GPU validation depends on local CUDA support.")
        return "needs_setup", notes
    if tool_id == "test-in-windows":
        return ("available" if _is_windows() else "unsupported_on_device"), notes
    if tool_id in {"test-in-macos", "test-in-ios", "test-in-safari"}:
        return ("available" if _is_macos() else "unsupported_on_device"), notes
    if tool_id in {"test-in-android", "test-in-raspberry-pi-os", "test-in-chromebook-os"}:
        return "needs_setup", notes
    if provider == "codex" and tool_id == "security-review":
        notes.append("Codex-backed security review can stay local-first without API keys.")
    return "coming_soon", notes


def default_permission_policy(tool_id: str) -> str:
    if tool_id in {"file-search", "format-changer", "write-publishable-docs", "goal-reminder", "ascii-image-creator"}:
        return "ask_once_per_project"
    if tool_id in {"deploy-with-vercel", "github-deployment-creator", "extra-sandbox", "cuda-test-environment"}:
        return "ask_every_time"
    return "ask_every_time"


def catalog_with_permissions(
    *,
    provider: str,
    connected_accounts: dict[str, Any],
    permission_overrides: dict[str, Any],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for item in TOOL_CATALOG:
        availability, notes = _availability(item["id"], provider=provider, connected_accounts=connected_accounts)
        permission_policy = str(permission_overrides.get(item["id"]) or default_permission_policy(item["id"]))
        items.append(
            {
                **item,
                "availability": availability,
                "permission_policy": permission_policy,
                "notes": notes,
            }
        )
    return items
