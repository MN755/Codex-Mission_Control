from __future__ import annotations

from mission_control_mcp_server import catalog


def test_catalog_falls_back_to_packaged_assets_without_repo_root(monkeypatch) -> None:
    monkeypatch.setattr(catalog, "_find_repo_root", lambda: None)
    catalog.load_plugin_manifest.cache_clear()
    catalog.load_resource_catalog.cache_clear()
    catalog.load_prompt_catalog.cache_clear()

    try:
        manifest = catalog.load_plugin_manifest()
        resources = catalog.resource_entries()
        prompts = catalog.prompt_entries()
    finally:
        catalog.load_plugin_manifest.cache_clear()
        catalog.load_resource_catalog.cache_clear()
        catalog.load_prompt_catalog.cache_clear()

    assert manifest["name"] == "mission-control"
    assert any(entry["uri_template"] == "mission-control://projects/{project_id}/status" for entry in resources)
    assert any(entry["name"] == "continue_orchestration" for entry in prompts)
