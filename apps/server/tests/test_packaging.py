from __future__ import annotations

import importlib.util
import json
import sys
from fastapi.testclient import TestClient
from pathlib import Path


def _load_packaging_module():
    root = Path(__file__).resolve().parents[3]
    module_path = root / "scripts" / "package-desktop.py"
    spec = importlib.util.spec_from_file_location("package_desktop", module_path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_desktop_app_module():
    root = Path(__file__).resolve().parents[3]
    module_path = root / "apps" / "desktop" / "src" / "mission_control_desktop" / "app.py"
    spec = importlib.util.spec_from_file_location("mission_control_desktop_app_test", module_path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_server_config_module():
    root = Path(__file__).resolve().parents[3]
    module_path = root / "apps" / "server" / "src" / "config.py"
    spec = importlib.util.spec_from_file_location("mission_control_server_config_test", module_path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_packaging_data_separator_matches_platform_conventions() -> None:
    module = _load_packaging_module()
    assert module.data_separator("windows") == ";"
    assert module.data_separator("linux") == ":"
    assert module.data_separator("macos") == ":"


def test_windows_pyinstaller_command_includes_onefile_and_model_assets(monkeypatch) -> None:
    module = _load_packaging_module()
    monkeypatch.setattr(module, "_package_is_importable", lambda _name: False)
    command = module.build_pyinstaller_command(
        "windows",
        Path("C:/dist"),
        Path("C:/build"),
        Path("C:/spec"),
    )
    assert "--onefile" in command
    assert "--noconsole" in command
    assert "--icon" in command
    assert any(str(module.WINDOWS_ICON_PATH) == part for part in command)
    assert any("frontend_dist" in part and ";" in part for part in command)
    assert any("mission-control.config.json" in part and ";" in part for part in command)


def test_macos_pyinstaller_command_builds_app_bundle(monkeypatch) -> None:
    module = _load_packaging_module()
    monkeypatch.setattr(module, "_package_is_importable", lambda _name: False)
    command = module.build_pyinstaller_command(
        "macos",
        Path("/tmp/dist"),
        Path("/tmp/build"),
        Path("/tmp/spec"),
    )
    assert "--windowed" in command
    assert "--onedir" in command
    assert "--osx-bundle-identifier" in command


def test_linux_pyinstaller_command_uses_posix_data_separator(monkeypatch) -> None:
    module = _load_packaging_module()
    monkeypatch.setattr(module, "_package_is_importable", lambda _name: False)
    command = module.build_pyinstaller_command(
        "linux",
        Path("/tmp/dist"),
        Path("/tmp/build"),
        Path("/tmp/spec"),
    )
    assert "--windowed" in command
    assert "--onedir" in command
    assert any("frontend_dist" in part and ":" in part for part in command)


def test_icon_asset_paths_exist() -> None:
    module = _load_packaging_module()
    assert module.ICON_GENERATOR.exists()
    assert module.SOURCE_LOGO_PATH.exists()
    assert module.WINDOWS_ICON_PATH.exists()
    assert module.LINUX_ICON_PNG.exists()


def test_macos_iconset_root_uses_required_extension() -> None:
    module = _load_packaging_module()
    assert module.macos_iconset_root().name.endswith(".iconset")


def test_appimagetool_env_enables_extract_and_run(monkeypatch) -> None:
    module = _load_packaging_module()
    monkeypatch.delenv("APPIMAGE_EXTRACT_AND_RUN", raising=False)
    env = module.appimagetool_env()
    assert env["APPIMAGE_EXTRACT_AND_RUN"] == "1"


def test_package_workflow_declares_read_only_permissions() -> None:
    workflow_path = Path(__file__).resolve().parents[3] / ".github" / "workflows" / "package-desktop.yml"
    workflow_text = workflow_path.read_text(encoding="utf-8")
    assert "permissions:" in workflow_text
    assert "contents: read" in workflow_text


def test_package_workflow_smoke_tests_editable_installs_and_node24_actions() -> None:
    workflow_path = Path(__file__).resolve().parents[3] / ".github" / "workflows" / "package-desktop.yml"
    workflow_text = workflow_path.read_text(encoding="utf-8")
    assert "actions/checkout@v5" in workflow_text
    assert "actions/setup-node@v5" in workflow_text
    assert "actions/setup-python@v6" in workflow_text
    assert "actions/upload-artifact@v6" in workflow_text
    assert 'python -c "import mission_control_desktop; import main"' in workflow_text
    assert "MISSION_CONTROL_DESKTOP_SMOKE_TEST=1 mission-control-desktop" in workflow_text


def test_launcher_scripts_use_configured_launcher_dir() -> None:
    root = Path(__file__).resolve().parents[3]
    start_script = (root / "scripts" / "start-mission-control.sh").read_text(encoding="utf-8")
    start_script_ps1 = (root / "scripts" / "start-mission-control.ps1").read_text(encoding="utf-8")
    start_daemon_script_ps1 = (root / "scripts" / "start-mission-control-daemon.ps1").read_text(encoding="utf-8")
    start_daemon_script_sh = (root / "scripts" / "start-mission-control-daemon.sh").read_text(encoding="utf-8")
    stop_daemon_script_sh = (root / "scripts" / "stop-mission-control-daemon.sh").read_text(encoding="utf-8")
    stop_script = (root / "scripts" / "stop-mission-control.ps1").read_text(encoding="utf-8")
    desktop_app = (root / "apps" / "desktop" / "src" / "mission_control_desktop" / "app.py").read_text(encoding="utf-8")
    assert 'MISSION_CONTROL_LAUNCHER_DIR="${LAUNCHER_DIR}"' in start_script
    assert 'MISSION_CONTROL_LAUNCHER_CONFIG' in start_script
    assert 'assert_local_host' in start_script
    assert "launcherLogDir" in start_script
    assert '--mode' in start_script
    assert 'MODE="desktop"' in start_script
    assert 'if [[ "${MODE}" == "desktop" ]]' in start_script
    assert 'build_frontend_if_needed' in start_script
    assert 'if [[ -d "${FRONTEND_DIST}" ]]; then' in start_script
    assert 'npm was not found on PATH, and the frontend bundle is missing' in start_script
    assert '-m uvicorn main:app --app-dir src' in start_script
    assert 'MISSION_CONTROL_API_BASE_URL' in start_script_ps1
    assert 'MISSION_CONTROL_BACKEND_URL' in start_script_ps1
    assert 'MISSION_CONTROL_LAUNCHER_CONFIG' in start_script_ps1
    assert 'Assert-LocalHost' in start_script_ps1
    assert 'MISSION_CONTROL_LAUNCHER_CONFIG' in start_daemon_script_ps1
    assert 'MISSION_CONTROL_LAUNCHER_DIR' in start_daemon_script_ps1
    assert 'MISSION_CONTROL_LAUNCHER_CONFIG' in start_daemon_script_sh
    assert 'MISSION_CONTROL_LAUNCHER_DIR' in start_daemon_script_sh
    assert 'launcherLogDir' in start_daemon_script_sh
    assert 'MISSION_CONTROL_LAUNCHER_CONFIG' in stop_daemon_script_sh
    assert "Frontend build not found. Run `" in desktop_app
    assert "in apps/dashboard first" in desktop_app
    assert "_frontend_build_command" in desktop_app
    assert "npm.cmd run build" not in desktop_app
    assert "launcherLogDir" in stop_script
    assert 'Join-Path $launcherDir "pids.json"' in stop_script


def test_desktop_app_ignores_fake_site_packages_repo_roots(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("MISSION_CONTROL_REPO_ROOT", raising=False)
    module = _load_desktop_app_module()
    monkeypatch.delenv("MISSION_CONTROL_REPO_ROOT", raising=False)
    fake_path = tmp_path / "site-packages" / "mission_control_desktop" / "app.py"
    fake_path.parent.mkdir(parents=True, exist_ok=True)
    fake_path.write_text("# placeholder\n", encoding="utf-8")

    assert module._discover_source_repo_root(fake_path) is None


def test_desktop_app_loads_backend_from_installed_modules(monkeypatch, tmp_path) -> None:
    module = _load_desktop_app_module()
    app_support_root = tmp_path / "app-home"
    ensure_calls: list[str] = []
    fake_app = object()
    original_import = module.importlib.import_module

    class FakeConfigModule:
        APP_SUPPORT_ROOT = app_support_root

        @staticmethod
        def ensure_runtime_dirs() -> None:
            ensure_calls.append("called")

    class FakeMainModule:
        app = fake_app

    def fake_import(name: str):
        if name == "config":
            return FakeConfigModule
        if name == "main":
            return FakeMainModule
        return original_import(name)

    monkeypatch.setattr(module, "SOURCE_REPO_ROOT", None)
    monkeypatch.setattr(module, "SERVER_SRC", None)
    monkeypatch.setattr(module.importlib, "import_module", fake_import)

    loaded_root, ensure_runtime_dirs, loaded_app = module._load_backend_runtime()
    ensure_runtime_dirs()

    assert loaded_root == app_support_root
    assert loaded_app is fake_app
    assert ensure_calls == ["called"]


def test_desktop_app_skips_missing_packaged_frontend_override(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("MISSION_CONTROL_FRONTEND_DIST", raising=False)
    module = _load_desktop_app_module()
    monkeypatch.setattr(module, "SOURCE_REPO_ROOT", None)
    monkeypatch.setattr(module, "FRONTEND_DIST", tmp_path / "missing-frontend-dist")

    assert module._default_frontend_dist_override() is None


def test_packaged_server_falls_back_to_default_bundle_when_frontend_env_is_stale(monkeypatch, tmp_path) -> None:
    if "main" not in sys.modules:
        import main  # noqa: F401
    import main

    dist = tmp_path / "frontend_dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html><body>SERVER BUNDLE</body></html>", encoding="utf-8")
    monkeypatch.setenv("MISSION_CONTROL_FRONTEND_DIST", str(tmp_path / "missing-frontend-dist"))
    monkeypatch.setattr(main, "RUNNING_FROM_SOURCE", False)
    monkeypatch.setattr(main, "default_frontend_dist_root", lambda: dist)

    client = TestClient(main.app)
    response = client.get("/")

    assert response.status_code == 200
    assert "SERVER BUNDLE" in response.text


def test_server_config_uses_launcher_log_dir_for_launcher_root(monkeypatch, tmp_path) -> None:
    config_path = tmp_path / "mission-control.config.json"
    config_path.write_text(json.dumps({"launcherLogDir": "custom-launcher"}), encoding="utf-8")
    monkeypatch.delenv("MISSION_CONTROL_LAUNCHER_DIR", raising=False)
    monkeypatch.setenv("MISSION_CONTROL_APP_HOME", str(tmp_path / "app-home"))
    monkeypatch.setenv("MISSION_CONTROL_LAUNCHER_CONFIG", str(config_path))

    module = _load_server_config_module()
    monkeypatch.setattr(module, "SOURCE_REPO_ROOT", None)
    monkeypatch.setattr(module, "RUNNING_FROM_SOURCE", False)
    monkeypatch.setattr(module, "APP_SUPPORT_ROOT", (tmp_path / "app-home").resolve())

    assert module.load_launcher_config()["launcherLogDir"] == "custom-launcher"
    assert module.resolve_launcher_root() == (tmp_path / "app-home" / "custom-launcher").resolve()


def test_packaged_server_serves_embedded_frontend_when_bundle_is_missing(monkeypatch) -> None:
    if "main" not in sys.modules:
        import main  # noqa: F401
    import main

    monkeypatch.setattr(main, "_frontend_dist_dir", lambda: None)
    monkeypatch.setattr(main, "RUNNING_FROM_SOURCE", False)

    client = TestClient(main.app)
    response = client.get("/")

    assert response.status_code == 200
    assert "Codex Mission Control" in response.text
