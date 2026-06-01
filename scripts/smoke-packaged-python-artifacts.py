from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from importlib.util import find_spec
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_DIRS = [
    ROOT / "apps" / "server",
    ROOT / "apps" / "desktop",
    ROOT / "apps" / "mcp-server",
]


def _run(args: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> None:
    subprocess.run(args, cwd=str(cwd), env=env, check=True)


def _ensure_build_toolchain(*, work_root: Path) -> None:
    if find_spec("wheel") is not None:
        return
    _run([sys.executable, "-m", "pip", "install", "--no-cache-dir", "wheel"], cwd=work_root)


def _stage_package_sources(build_root: Path) -> list[Path]:
    staged_dirs: list[Path] = []
    for package_dir in PACKAGE_DIRS:
        staged_dir = build_root / package_dir.name
        shutil.copytree(package_dir, staged_dir, dirs_exist_ok=True)
        staged_dirs.append(staged_dir)
    return staged_dirs


def _build_wheels(wheelhouse: Path, *, build_root: Path) -> None:
    _ensure_build_toolchain(work_root=build_root)
    for staged_dir in _stage_package_sources(build_root):
        _run(
            [
                sys.executable,
                "-m",
                "pip",
                "wheel",
                "--no-cache-dir",
                "--no-build-isolation",
                "--no-deps",
                "--wheel-dir",
                str(wheelhouse),
                ".",
            ],
            cwd=staged_dir,
        )


def _install_wheels(wheelhouse: Path, target: Path, *, work_root: Path) -> list[Path]:
    wheels = sorted(wheelhouse.glob("*.whl"))
    if len(wheels) < len(PACKAGE_DIRS):
        raise RuntimeError(f"Expected at least {len(PACKAGE_DIRS)} wheels, found {len(wheels)} in {wheelhouse}.")
    _run(
        [sys.executable, "-m", "pip", "install", "--no-cache-dir", "--no-deps", "--target", str(target), *[str(path) for path in wheels]],
        cwd=work_root,
    )
    return wheels


def _smoke_packaged_install(target: Path, *, cwd: Path) -> None:
    smoke_code = """
import importlib
import importlib.resources
import os
from pathlib import Path

from mission_control_mcp_server import catalog

plugin = catalog.load_plugin_manifest()
resources = catalog.load_resource_catalog()
prompts = catalog.load_prompt_catalog()
assert plugin["name"] == "mission-control"
assert resources["resources"], "Missing bundled resources catalog"
assert prompts["prompts"], "Missing bundled prompts catalog"
bundled_files = importlib.resources.files("mission_control_mcp_server._bundled")
assert (bundled_files / ".codex-plugin" / "plugin.json").is_file(), "Missing bundled Codex plugin manifest"

desktop_app = importlib.import_module("mission_control_desktop.app")
assert desktop_app.SOURCE_REPO_ROOT is None

server_main = importlib.import_module("main")
assert hasattr(server_main, "app")
assert os.getcwd() == str(Path.cwd())
print("packaged-smoke-ok")
"""
    env = dict(os.environ)
    env["PYTHONPATH"] = str(target)
    env["MISSION_CONTROL_APP_HOME"] = str(cwd / "app-home")
    _run([sys.executable, "-c", smoke_code], cwd=cwd, env=env)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="mc-packaged-smoke-") as temp_dir:
        temp_root = Path(temp_dir)
        wheelhouse = temp_root / "wheelhouse"
        build_root = temp_root / "build-sources"
        install_target = temp_root / "site-packages"
        smoke_cwd = temp_root / "outside-source-tree"
        build_root.mkdir(parents=True, exist_ok=True)
        wheelhouse.mkdir(parents=True, exist_ok=True)
        install_target.mkdir(parents=True, exist_ok=True)
        smoke_cwd.mkdir(parents=True, exist_ok=True)

        _build_wheels(wheelhouse, build_root=build_root)
        wheels = _install_wheels(wheelhouse, install_target, work_root=temp_root)
        _smoke_packaged_install(install_target, cwd=smoke_cwd)
        print(f"Packaged smoke passed with {len(wheels)} built artifacts.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
