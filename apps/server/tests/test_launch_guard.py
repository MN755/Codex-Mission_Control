from __future__ import annotations

from launch_guard import LaunchGuardMetrics, LaunchGuardPolicy, evaluate_launch_guard


def _policy() -> LaunchGuardPolicy:
    return LaunchGuardPolicy(
        enabled=True,
        hard_total_token_budget=1000,
        hard_total_worker_launch_budget=5,
        hard_peak_context_budget=800,
        quota_backoff_cooldown_minutes=60,
    )


def test_launch_guard_allows_healthy_codex_worker() -> None:
    decision = evaluate_launch_guard(
        policy=_policy(),
        metrics=LaunchGuardMetrics(total_tokens=120, worker_launch_count=1, peak_context_tokens=200),
        provider="codex",
        role="worker",
        model="gpt-5.4-mini",
    )

    assert decision.allowed is True
    assert decision.status == "ok"


def test_launch_guard_blocks_non_whitelisted_codex_worker_model() -> None:
    decision = evaluate_launch_guard(
        policy=_policy(),
        metrics=LaunchGuardMetrics(total_tokens=120, worker_launch_count=1, peak_context_tokens=200),
        provider="codex",
        role="worker",
        model="gpt-5.4",
    )

    assert decision.allowed is False
    assert decision.status == "blocked_model_policy"


def test_launch_guard_blocks_launch_budget_exhaustion() -> None:
    decision = evaluate_launch_guard(
        policy=_policy(),
        metrics=LaunchGuardMetrics(total_tokens=120, worker_launch_count=5, peak_context_tokens=200),
        provider="codex",
        role="worker",
        model="gpt-5.4-mini",
    )

    assert decision.allowed is False
    assert decision.status == "blocked_launch_budget"


def test_launch_guard_blocks_total_token_budget_exhaustion() -> None:
    decision = evaluate_launch_guard(
        policy=_policy(),
        metrics=LaunchGuardMetrics(total_tokens=1000, worker_launch_count=2, peak_context_tokens=200),
        provider="codex",
        role="worker",
        model="gpt-5.4-mini",
    )

    assert decision.allowed is False
    assert decision.status == "blocked_token_budget"


def test_launch_guard_blocks_peak_context_budget_exhaustion() -> None:
    decision = evaluate_launch_guard(
        policy=_policy(),
        metrics=LaunchGuardMetrics(total_tokens=120, worker_launch_count=2, peak_context_tokens=800),
        provider="codex",
        role="worker",
        model="gpt-5.4-mini",
    )

    assert decision.allowed is False
    assert decision.status == "blocked_context_budget"


def test_launch_guard_blocks_provider_backoff_before_any_new_launch() -> None:
    decision = evaluate_launch_guard(
        policy=_policy(),
        metrics=LaunchGuardMetrics(
            total_tokens=120,
            worker_launch_count=2,
            peak_context_tokens=200,
            quota_backoff_active=True,
            quota_backoff_summary="You've hit your usage limit. Try again later.",
        ),
        provider="codex",
        role="worker",
        model="gpt-5.4-mini",
    )

    assert decision.allowed is False
    assert decision.status == "provider_backoff_active"
    assert "usage limit" in (decision.reason or "")
