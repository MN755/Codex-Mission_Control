from __future__ import annotations

from usage_tracking import (
    accumulate_usage_rollup,
    build_prompt_usage_estimate,
    empty_usage_rollup,
    merge_usage_snapshots,
    usage_snapshot_from_event,
)


def test_usage_snapshot_from_event_normalizes_token_and_context_metrics() -> None:
    event = {
        "type": "turn.completed",
        "usage": {
            "input_tokens": 120,
            "output_tokens": 30,
            "cached_input_tokens": 10,
            "reasoning_tokens": 4,
            "context_window_tokens": 1000,
        },
    }

    snapshot = usage_snapshot_from_event(event)

    assert snapshot is not None
    assert snapshot["input_tokens"] == 120
    assert snapshot["output_tokens"] == 30
    assert snapshot["total_tokens"] == 150
    assert snapshot["cached_input_tokens"] == 10
    assert snapshot["reasoning_tokens"] == 4
    assert snapshot["context_tokens"] == 120
    assert snapshot["peak_context_tokens"] == 120
    assert snapshot["context_window_tokens"] == 1000
    assert snapshot["context_utilization"] == 0.12
    assert snapshot["estimated"] is False


def test_merge_usage_snapshots_promotes_actual_usage_over_estimates() -> None:
    estimate = build_prompt_usage_estimate("x" * 400)
    actual = usage_snapshot_from_event(
        {
            "type": "turn.completed",
            "usage": {
                "prompt_tokens": 90,
                "completion_tokens": 15,
                "max_input_tokens": 1000,
            },
        }
    )

    merged = merge_usage_snapshots(estimate, actual)

    assert merged["estimated_input_tokens"] == estimate["estimated_input_tokens"]
    assert merged["input_tokens"] == 90
    assert merged["output_tokens"] == 15
    assert merged["total_tokens"] == 105
    assert merged["context_tokens"] == 90
    assert merged["peak_context_tokens"] == 100
    assert merged["context_window_tokens"] == 1000
    assert merged["peak_context_utilization"] == 0.09
    assert merged["estimated"] is False


def test_usage_snapshot_from_event_supports_nested_aliases_and_cache_read_fields() -> None:
    event = {
        "result": {
            "usage": {
                "inputTokens": "250",
                "outputTokens": "40",
                "cacheReadInputTokens": 25,
                "output_token_details": {"reasoning": 6},
                "prompt_token_details": {"total_tokens": 260},
                "max_context_tokens": 2000,
            }
        }
    }

    snapshot = usage_snapshot_from_event(event)

    assert snapshot is not None
    assert snapshot["source"] == "result.usage"
    assert snapshot["input_tokens"] == 250
    assert snapshot["output_tokens"] == 40
    assert snapshot["total_tokens"] == 290
    assert snapshot["cached_input_tokens"] == 25
    assert snapshot["reasoning_tokens"] == 6
    assert snapshot["context_tokens"] == 260
    assert snapshot["peak_context_tokens"] == 260
    assert snapshot["context_window_tokens"] == 2000
    assert snapshot["context_utilization"] == 0.13


def test_accumulate_usage_rollup_preserves_peak_context_and_window_from_mixed_sources() -> None:
    rollup = empty_usage_rollup()
    first = usage_snapshot_from_event(
        {
            "usage_metadata": {
                "prompt_tokens": 100,
                "completion_tokens": 20,
                "max_prompt_tokens": 1000,
            }
        }
    )
    second = merge_usage_snapshots(
        build_prompt_usage_estimate("x" * 800),
        usage_snapshot_from_event(
            {
                "data": {
                    "usage": {
                        "input_tokens": 180,
                        "output_tokens": 10,
                        "context_window_tokens": 1500,
                    }
                }
            }
        ),
    )

    accumulate_usage_rollup(rollup, first)
    accumulate_usage_rollup(rollup, second)

    assert rollup["input_tokens"] == 280
    assert rollup["output_tokens"] == 30
    assert rollup["total_tokens"] == 310
    assert rollup["peak_context_tokens"] == 200
    assert rollup["context_window_tokens"] == 1500
    assert rollup["peak_context_utilization"] == 0.12
