from __future__ import annotations


def test_capability_benchmark_rejects_unknown_category(client) -> None:
    response = client.post(
        "/api/capabilities/benchmarks",
        json={
            "provider": "test",
            "model": "demo",
            "runner_mode": "auto",
            "category": "totally_made_up",
            "score": 77,
            "sample_size": 1,
        },
    )
    assert response.status_code == 422
    assert "Category must be one of" in response.text
