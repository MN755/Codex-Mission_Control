from __future__ import annotations

from spatial3d_starters import (
    generate_spatial3d_feature_bundle,
    get_spatial3d_feature_catalog_entry,
    spatial3d_feature_catalog,
)


def test_spatial3d_feature_catalog_covers_requested_feature_families() -> None:
    payload = spatial3d_feature_catalog()

    assert len(payload) == 20
    feature_ids = {item["feature_id"] for item in payload}
    assert "asset_pipeline" in feature_ids
    assert "blender_integration" in feature_ids
    assert "geospatial_gis" in feature_ids
    assert "research_to_code" in feature_ids


def test_spatial3d_feature_bundle_returns_real_bundle_content() -> None:
    bundle = generate_spatial3d_feature_bundle("browser_renderer")

    assert bundle["feature_id"] == "browser_renderer"
    assert bundle["variant"] == "default"
    assert "spatial3d_starters/browser_render_probe.ts" in bundle["files"]
    assert "Playwright" in bundle["files"]["spatial3d_starters/browser_render_probe.ts"]
    assert any("scene readiness" in step.lower() for step in bundle["validation_steps"])


def test_spatial3d_feature_bundle_supports_multiple_requested_domains() -> None:
    usd_bundle = generate_spatial3d_feature_bundle("houdini_usd")
    ffmpeg_bundle = generate_spatial3d_feature_bundle("codec_video_pipeline")
    gis_bundle = generate_spatial3d_feature_bundle("geospatial_gis")

    assert "pxr" in usd_bundle["files"]["spatial3d_starters/usd_stage_check.py"]
    assert "ffmpeg" in ffmpeg_bundle["files"]["spatial3d_starters/ffmpeg_workflow.md"].lower()
    assert "pyproj" in gis_bundle["files"]["spatial3d_starters/crs_validator.py"]


def test_spatial3d_feature_bundle_rejects_bad_feature_and_variant() -> None:
    try:
        get_spatial3d_feature_catalog_entry("not-real")
    except ValueError as exc:
        assert "Unknown spatial 3D feature bundle" in str(exc)
    else:
        raise AssertionError("Expected missing feature to fail")

    try:
        generate_spatial3d_feature_bundle("asset_pipeline", variant="bad")
    except ValueError as exc:
        assert "Unsupported spatial 3D feature variant" in str(exc)
    else:
        raise AssertionError("Expected bad variant to fail")
