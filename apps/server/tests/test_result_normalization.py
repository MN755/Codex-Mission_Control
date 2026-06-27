from __future__ import annotations

import json

from result_normalization import (
    build_normalized_result_rollup,
    classify_evidence_artifacts,
    load_normalized_result_rollup_summary,
    write_normalized_result_rollup,
)


def test_classify_evidence_artifacts_groups_native_and_browser_evidence() -> None:
    inventory = classify_evidence_artifacts(
        [
            "artifacts/logs/device.log",
            "artifacts/screenshots/home.png",
            "artifacts/traces/playwright-trace.zip",
            "artifacts/crashes/app.crash",
            "artifacts/coverage/lcov.info",
            "artifacts/perf/fps-benchmark.json",
            "artifacts/screenshots/home.png",
        ]
    )

    assert inventory["categories"]["logs"] == ["artifacts/logs/device.log"]
    assert inventory["categories"]["screenshots"] == ["artifacts/screenshots/home.png"]
    assert inventory["categories"]["traces"] == ["artifacts/traces/playwright-trace.zip"]
    assert inventory["categories"]["crashes"] == ["artifacts/crashes/app.crash"]
    assert inventory["categories"]["coverage"] == ["artifacts/coverage/lcov.info"]
    assert inventory["categories"]["performance"] == ["artifacts/perf/fps-benchmark.json"]
    assert inventory["categories_present"] == ["logs", "screenshots", "traces", "crashes", "coverage", "performance"]


def test_build_and_load_normalized_result_rollup_round_trip(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    summaries = [
        {
            "status": "passed",
            "engine": "unity",
            "output_artifact": "artifacts/game-engine-governance/unity-editmode-summary.json",
            "warning_count": 1,
        },
        {
            "status": "missing",
            "engine": "unreal",
            "output_artifact": "artifacts/game-engine-governance/unreal-automation-summary.json",
            "warning_count": 0,
        },
    ]

    rollup = build_normalized_result_rollup(
        summaries=summaries,
        blocking_statuses=["missing", "failed", "parse_error"],
        metadata={"selected_target_id": "win-unity", "recommended_runner_lane": "unity"},
    )
    rollup_path = write_normalized_result_rollup(
        workspace,
        "artifacts/game-engine-governance/normalized-results-summary.json",
        rollup,
    )
    loaded = load_normalized_result_rollup_summary(
        workspace,
        "artifacts/game-engine-governance/normalized-results-summary.json",
    )

    assert json.loads(rollup_path.read_text(encoding="utf-8"))["blocking_summary_ids"] == [
        "artifacts/game-engine-governance/unreal-automation-summary.json"
    ]
    assert loaded["normalized_results_summary_path"] == "artifacts/game-engine-governance/normalized-results-summary.json"
    assert loaded["normalized_summary_count"] == 2
    assert loaded["normalized_passed_count"] == 1
    assert loaded["normalized_missing_count"] == 1
    assert loaded["normalized_publish_ready"] is False
