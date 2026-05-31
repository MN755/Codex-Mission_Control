from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_DIRS = [
    ROOT / "apps" / "server",
    ROOT / "apps" / "desktop",
    ROOT / "apps" / "mcp-server",
]


def _run(args: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> None:
    subprocess.run(args, cwd=str(cwd), env=env, check=True)


def _build_wheels(wheelhouse: Path) -> None:
    for package_dir in PACKAGE_DIRS:
        _run(
            [sys.executable, "-m", "pip", "wheel", "--no-cache-dir", "--no-build-isolation", "--no-deps", "--wheel-dir", str(wheelhouse), str(package_dir)],
            cwd=ROOT,
        )


def _install_wheels(wheelhouse: Path, target: Path) -> list[Path]:
    wheels = sorted(wheelhouse.glob("*.whl"))
    if len(wheels) < len(PACKAGE_DIRS):
        raise RuntimeError(f"Expected at least {len(PACKAGE_DIRS)} wheels, found {len(wheels)} in {wheelhouse}.")
    _run(
        [sys.executable, "-m", "pip", "install", "--no-cache-dir", "--no-deps", "--target", str(target), *[str(path) for path in wheels]],
        cwd=ROOT,
    )
    return wheels


def _smoke_packaged_install(target: Path, *, cwd: Path) -> None:
    smoke_code = """
import importlib
import os
from pathlib import Path

from mission_control_mcp_server import catalog

plugin = catalog.load_plugin_manifest()
resources = catalog.load_resource_catalog()
prompts = catalog.load_prompt_catalog()
assert plugin["name"] == "mission-control"
assert resources["resources"], "Missing bundled resources catalog"
assert prompts["prompts"], "Missing bundled prompts catalog"

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
        install_target = temp_root / "site-packages"
        smoke_cwd = temp_root / "outside-source-tree"
        wheelhouse.mkdir(parents=True, exist_ok=True)
        install_target.mkdir(parents=True, exist_ok=True)
        smoke_cwd.mkdir(parents=True, exist_ok=True)

        _build_wheels(wheelhouse)
        wheels = _install_wheels(wheelhouse, install_target)
        _smoke_packaged_install(install_target, cwd=smoke_cwd)
        print(f"Packaged smoke passed with {len(wheels)} built artifacts.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
