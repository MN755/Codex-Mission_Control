from __future__ import annotations

import importlib
import json
import os
import socket
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path
from typing import Any, Callable

IS_FROZEN = bool(getattr(sys, "frozen", False))
BUNDLE_ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))


def _discover_source_repo_root(current_file: str | Path | None = None) -> Path | None:
    explicit = os.environ.get("MISSION_CONTROL_REPO_ROOT")
    if explicit:
        candidate = Path(explicit).expanduser().resolve()
        if (candidate / "apps" / "server" / "src" / "main.py").exists() and (candidate / "README.md").exists():
            return candidate
    file_path = Path(current_file or __file__).resolve()
    for parent in file_path.parents:
        if (parent / "apps" / "server" / "src" / "main.py").exists() and (parent / "README.md").exists():
            return parent
    return None


SOURCE_REPO_ROOT = None if IS_FROZEN else _discover_source_repo_root()
SERVER_SRC = (SOURCE_REPO_ROOT / "apps" / "server" / "src") if SOURCE_REPO_ROOT is not None else None
FRONTEND_DIST = (
    (SOURCE_REPO_ROOT / "apps" / "dashboard" / "dist")
    if SOURCE_REPO_ROOT is not None
    else (BUNDLE_ROOT / "frontend_dist")
)

if SERVER_SRC is not None and str(SERVER_SRC) not in sys.path:
    sys.path.insert(0, str(SERVER_SRC))

if SOURCE_REPO_ROOT is not None or FRONTEND_DIST.exists():
    os.environ.setdefault("MISSION_CONTROL_FRONTEND_DIST", str(FRONTEND_DIST))
if SOURCE_REPO_ROOT is not None:
    os.environ.setdefault("MISSION_CONTROL_REPO_ROOT", str(SOURCE_REPO_ROOT))


def _frontend_build_command() -> str:
    if sys.platform == "win32":
        return "npm run build"
    return "npm run build"


def _write_launcher_metadata(port: int, *, app_support_root: Path) -> None:
    launcher_dir = os.environ.get("MISSION_CONTROL_LAUNCHER_DIR")
    if not launcher_dir:
        return
    launcher_path = Path(launcher_dir)
    launcher_path.mkdir(parents=True, exist_ok=True)
    payload = {
        "repoRoot": str(SOURCE_REPO_ROOT) if SOURCE_REPO_ROOT is not None else None,
        "appSupportRoot": str(app_support_root),
        "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "mode": "desktop",
        "desktop": {
            "pid": os.getpid(),
            "server_port": port,
            "frontend_dist": os.environ.get("MISSION_CONTROL_FRONTEND_DIST", str(FRONTEND_DIST)),
        },
    }
    (launcher_path / "pids.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _find_free_port(host: str) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


def _wait_for_server(url: str, timeout_seconds: float = 20.0) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:  # noqa: S310
                if response.status == 200:
                    return
        except Exception:
            time.sleep(0.2)
    raise RuntimeError(f"Timed out waiting for {url}")


def _load_backend_runtime() -> tuple[Path, Callable[[], None], Any]:
    if SERVER_SRC is not None and SERVER_SRC.exists() and str(SERVER_SRC) not in sys.path:
        sys.path.insert(0, str(SERVER_SRC))
    config_module = importlib.import_module("config")
    main_module = importlib.import_module("main")
    return config_module.APP_SUPPORT_ROOT, config_module.ensure_runtime_dirs, main_module.app


def main() -> None:
    if os.environ.get("MISSION_CONTROL_DESKTOP_SMOKE_TEST") == "1":
        print("mission-control-desktop smoke ok", flush=True)
        return
    import uvicorn

    app_support_root, ensure_runtime_dirs, fastapi_app = _load_backend_runtime()

    ensure_runtime_dirs()
    if SOURCE_REPO_ROOT is not None and not FRONTEND_DIST.exists():
        raise SystemExit(
            f"Frontend build not found. Run `{_frontend_build_command()}` in apps/dashboard first, "
            "or use the launcher script that builds the desktop UI automatically."
        )

    try:
        import webview
    except ImportError as exc:  # pragma: no cover - runtime-only path
        raise SystemExit(
            "pywebview is required for desktop mode. Install the desktop dependencies first."
        ) from exc

    host = "127.0.0.1"
    port = _find_free_port(host)
    health_url = f"http://{host}:{port}/api/health"
    app_url = f"http://{host}:{port}/startup"

    config = uvicorn.Config(
        fastapi_app,
        host=host,
        port=port,
        log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    _wait_for_server(health_url)
    _write_launcher_metadata(port, app_support_root=app_support_root)

    def _shutdown() -> None:
        server.should_exit = True
        thread.join(timeout=5)

    preferred_gui = os.environ.get("MISSION_CONTROL_WEBVIEW_GUI")
    if preferred_gui is None and sys.platform == "win32":
        preferred_gui = "edgechromium"

    window = webview.create_window(
        "Codex Mission Control",
        app_url,
        width=1480,
        height=940,
        min_size=(1080, 720),
        background_color="#08111d",
    )
    window.events.closed += _shutdown

    try:
        if preferred_gui:
            webview.start(gui=preferred_gui)
        else:
            webview.start()
    except Exception as exc:  # pragma: no cover - runtime-only path
        print(f"[mission-control-desktop] Native webview failed: {exc}", flush=True)
        webbrowser.open(app_url)
        try:
            while thread.is_alive():
                time.sleep(1.0)
        except KeyboardInterrupt:
            pass
        finally:
            _shutdown()


__all__ = ["main", "_discover_source_repo_root", "_load_backend_runtime"]
