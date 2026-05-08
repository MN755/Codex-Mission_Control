from __future__ import annotations

import importlib.util
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
    assert module.ICON_PATH.exists()
