from __future__ import annotations

import argparse
import importlib.util
import os
import shutil
import stat
import subprocess
import sys
import tarfile
from pathlib import Path


APP_SLUG = "CodexMissionControl"
DISPLAY_NAME = "Codex Mission Control"
MACOS_BUNDLE_ID = "com.openai.codexmissioncontrol"
REPO_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIR = REPO_ROOT / "apps" / "dashboard"
FRONTEND_DIST = FRONTEND_DIR / "dist"
DESKTOP_SRC = REPO_ROOT / "apps" / "desktop" / "src"
SERVER_SRC = REPO_ROOT / "apps" / "server" / "src"
ICON_PATH = REPO_ROOT / "apps" / "desktop" / "assets" / "mission-control.svg"
DESKTOP_ENTRY_PATH = REPO_ROOT / "apps" / "desktop" / "packaging" / "linux" / "codex-mission-control.desktop"
OUTPUT_ROOT = REPO_ROOT / ".runtime" / "packages"


def current_platform() -> str:
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    return "linux"


def data_separator(platform_name: str) -> str:
    return ";" if platform_name.startswith("win") else ":"


def add_data_arg(source: Path, destination: str, platform_name: str) -> str:
    return f"{source}{data_separator(platform_name)}{destination}"


def ensure_frontend_bundle(force: bool) -> None:
    if FRONTEND_DIST.exists() and not force:
        return
    npm = shutil.which("npm.cmd") or shutil.which("npm")
    if npm is None:
        raise RuntimeError("npm was not found on PATH. Install Node.js and npm before packaging.")
    subprocess.run([npm, "run", "build"], cwd=FRONTEND_DIR, check=True)


def _package_is_importable(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def build_pyinstaller_command(platform_name: str, dist_root: Path, work_root: Path, spec_root: Path) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--name",
        APP_SLUG,
        "--distpath",
        str(dist_root),
        "--workpath",
        str(work_root),
        "--specpath",
        str(spec_root),
        "--paths",
        str(DESKTOP_SRC),
        "--paths",
        str(SERVER_SRC),
        "--add-data",
        add_data_arg(FRONTEND_DIST, "frontend_dist", platform_name),
        "--add-data",
        add_data_arg(REPO_ROOT / "scripts" / "mission-control.config.json", "scripts", platform_name),
        "--collect-submodules",
        "uvicorn",
        "--collect-submodules",
        "webview",
        "--collect-data",
        "webview",
        str(DESKTOP_SRC / "mission_control_desktop" / "__main__.py"),
    ]

    for optional_package in ("anyio", "pythonnet", "clr_loader"):
        if _package_is_importable(optional_package):
            command.extend(["--collect-submodules", optional_package])

    if platform_name == "windows":
        command.extend(["--onefile", "--noconsole"])
    elif platform_name == "macos":
        command.extend(["--windowed", "--onedir", "--osx-bundle-identifier", MACOS_BUNDLE_ID])
    else:
        command.extend(["--windowed", "--onedir"])
    return command


def _copy_tree(source: Path, destination: Path) -> None:
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination)


def build_with_pyinstaller(platform_name: str, output_root: Path) -> Path:
    dist_root = output_root / "dist" / platform_name
    work_root = output_root / "build" / platform_name
    spec_root = output_root / "spec" / platform_name
    for directory in (dist_root, work_root, spec_root):
        directory.mkdir(parents=True, exist_ok=True)
    command = build_pyinstaller_command(platform_name, dist_root, work_root, spec_root)
    subprocess.run(command, cwd=REPO_ROOT, check=True)
    if platform_name == "windows":
        return dist_root / f"{APP_SLUG}.exe"
    if platform_name == "macos":
        return dist_root / f"{APP_SLUG}.app"
    return dist_root / APP_SLUG


def _make_zip(source_path: Path, destination_without_suffix: Path) -> Path:
    archive_path = shutil.make_archive(str(destination_without_suffix), "zip", root_dir=source_path.parent, base_dir=source_path.name)
    return Path(archive_path)


def _make_targz(source_path: Path, destination: Path) -> Path:
    with tarfile.open(destination, "w:gz") as archive:
        archive.add(source_path, arcname=source_path.name)
    return destination


def package_windows(executable_path: Path, release_root: Path) -> list[Path]:
    release_root.mkdir(parents=True, exist_ok=True)
    archive = _make_zip(executable_path, release_root / APP_SLUG)
    return [executable_path, archive]


def package_macos(app_bundle: Path, release_root: Path) -> list[Path]:
    release_root.mkdir(parents=True, exist_ok=True)
    archive = _make_zip(app_bundle, release_root / APP_SLUG)
    return [app_bundle, archive]


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _create_linux_appdir(pyinstaller_bundle: Path, release_root: Path) -> Path:
    appdir = release_root / f"{APP_SLUG}.AppDir"
    if appdir.exists():
        shutil.rmtree(appdir)
    appdir.mkdir(parents=True, exist_ok=True)

    payload_root = appdir / "usr" / "lib" / APP_SLUG
    _copy_tree(pyinstaller_bundle, payload_root)

    icon_root = appdir / "codex-mission-control.svg"
    shutil.copy2(ICON_PATH, icon_root)
    shutil.copy2(ICON_PATH, appdir / ".DirIcon")
    shutil.copy2(DESKTOP_ENTRY_PATH, appdir / "codex-mission-control.desktop")

    apprun = appdir / "AppRun"
    _write_text(
        apprun,
        "\n".join(
            [
                "#!/bin/sh",
                'HERE="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"',
                'export APPDIR="$HERE"',
                f'exec "$HERE/usr/lib/{APP_SLUG}/{APP_SLUG}" "$@"',
            ]
        )
        + "\n",
    )
    apprun.chmod(apprun.stat().st_mode | stat.S_IEXEC)
    return appdir


def package_linux(pyinstaller_bundle: Path, release_root: Path) -> list[Path]:
    release_root.mkdir(parents=True, exist_ok=True)
    appdir = _create_linux_appdir(pyinstaller_bundle, release_root)
    artifacts: list[Path] = [appdir]

    tarball = _make_targz(pyinstaller_bundle, release_root / f"{APP_SLUG}-linux-portable.tar.gz")
    artifacts.append(tarball)

    appimagetool = os.environ.get("APPIMAGETOOL") or shutil.which("appimagetool")
    if appimagetool:
        appimage_path = release_root / f"{APP_SLUG}.AppImage"
        subprocess.run([appimagetool, str(appdir), str(appimage_path)], check=True)
        artifacts.append(appimage_path)
    return artifacts


def build_release(force_frontend: bool = False) -> list[Path]:
    platform_name = current_platform()
    ensure_frontend_bundle(force_frontend)
    output_root = OUTPUT_ROOT / platform_name
    release_root = output_root / "release"
    built_target = build_with_pyinstaller(platform_name, output_root)
    if platform_name == "windows":
        return package_windows(built_target, release_root)
    if platform_name == "macos":
        return package_macos(built_target, release_root)
    return package_linux(built_target, release_root)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build packaged Codex Mission Control desktop artifacts.")
    parser.add_argument("--force-frontend", action="store_true", help="Rebuild the frontend bundle before packaging.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    artifacts = build_release(force_frontend=args.force_frontend)
    for artifact in artifacts:
        print(artifact)


if __name__ == "__main__":
    main()
