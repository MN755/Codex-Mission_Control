from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


ALLOWED_CODEX_MANAGER_MODELS = {"gpt-5.4", "gpt-5.4-mini"}
ALLOWED_CODEX_WORKER_MODELS = {"gpt-5.4-mini"}


@dataclass(frozen=True)
class LaunchGuardPolicy:
    enabled: bool
    hard_total_token_budget: int
    hard_total_worker_launch_budget: int
    hard_peak_context_budget: int
    quota_backoff_cooldown_minutes: int


@dataclass(frozen=True)
class LaunchGuardMetrics:
    total_tokens: int = 0
    worker_launch_count: int = 0
    peak_context_tokens: int = 0
    quota_backoff_active: bool = False
    quota_backoff_until: datetime | None = None
    quota_backoff_summary: str | None = None


@dataclass(frozen=True)
class LaunchGuardDecision:
    allowed: bool
    status: str
    reason: str | None = None


def is_allowed_codex_manager_model(model: str | None) -> bool:
    return str(model or "").strip() in ALLOWED_CODEX_MANAGER_MODELS


def is_allowed_codex_worker_model(model: str | None) -> bool:
    return str(model or "").strip() in ALLOWED_CODEX_WORKER_MODELS


def evaluate_launch_guard(
    *,
    policy: LaunchGuardPolicy,
    metrics: LaunchGuardMetrics,
    provider: str,
    role: str,
    model: str | None,
) -> LaunchGuardDecision:
    if not policy.enabled:
        return LaunchGuardDecision(allowed=True, status="disabled")
    if provider == "codex" and role == "manager" and not is_allowed_codex_manager_model(model):
        return LaunchGuardDecision(
            allowed=False,
            status="blocked_model_policy",
            reason=(
                f"Codex manager launches are restricted to {', '.join(sorted(ALLOWED_CODEX_MANAGER_MODELS))}. "
                f"Refusing to start manager model {model or '<unset>'}."
            ),
        )
    if provider == "codex" and role == "worker" and not is_allowed_codex_worker_model(model):
        return LaunchGuardDecision(
            allowed=False,
            status="blocked_model_policy",
            reason=(
                f"Codex worker launches are restricted to {', '.join(sorted(ALLOWED_CODEX_WORKER_MODELS))}. "
                f"Refusing to start worker model {model or '<unset>'}."
            ),
        )
    if metrics.quota_backoff_active:
        summary = metrics.quota_backoff_summary or "A recent provider quota failure was detected."
        return LaunchGuardDecision(
            allowed=False,
            status="provider_backoff_active",
            reason=summary,
        )
    if metrics.worker_launch_count >= policy.hard_total_worker_launch_budget:
        return LaunchGuardDecision(
            allowed=False,
            status="blocked_launch_budget",
            reason=(
                "Worker launch budget exhausted: "
                f"{metrics.worker_launch_count}/{policy.hard_total_worker_launch_budget} launches used."
            ),
        )
    if metrics.total_tokens >= policy.hard_total_token_budget:
        return LaunchGuardDecision(
            allowed=False,
            status="blocked_token_budget",
            reason=(
                "Token budget exhausted: "
                f"{metrics.total_tokens}/{policy.hard_total_token_budget} total tokens observed."
            ),
        )
    if metrics.peak_context_tokens >= policy.hard_peak_context_budget:
        return LaunchGuardDecision(
            allowed=False,
            status="blocked_context_budget",
            reason=(
                "Peak context budget exhausted: "
                f"{metrics.peak_context_tokens}/{policy.hard_peak_context_budget} tokens observed."
            ),
        )
    return LaunchGuardDecision(allowed=True, status="ok")
