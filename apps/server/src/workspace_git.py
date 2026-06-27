from __future__ import annotations

import hashlib
import os
from pathlib import Path

from config import RUNTIME_ROOT


def _existing_global_gitconfig(env: dict[str, str] | None = None) -> Path | None:
    source = env or os.environ
    explicit = str(source.get("GIT_CONFIG_GLOBAL") or "").strip()
    if explicit:
        candidate = Path(explicit).expanduser().resolve()
        return candidate if candidate.exists() else None
    home_text = str(source.get("USERPROFILE") or source.get("HOME") or "").strip()
    if not home_text:
        return None
    candidate = Path(home_text).expanduser().resolve() / ".gitconfig"
    return candidate if candidate.exists() else None


def ensure_workspace_git_config(workspace_path: str | Path, *, env: dict[str, str] | None = None) -> Path:
    root = Path(workspace_path).expanduser().resolve()
    config_root = (RUNTIME_ROOT / "git-trust").resolve()
    config_root.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha1(str(root).encode("utf-8")).hexdigest()[:12]
    config_path = config_root / f"{digest}.gitconfig"
    include_path = _existing_global_gitconfig(env)
    lines: list[str] = []
    if include_path is not None and include_path != config_path:
        lines.extend([
            "[include]",
            f"\tpath = {include_path.as_posix()}",
            "",
        ])
    lines.extend([
        "[safe]",
        f"\tdirectory = {root.as_posix()}",
        "",
    ])
    content = "\n".join(lines)
    current = config_path.read_text(encoding="utf-8") if config_path.exists() else None
    if current != content:
        config_path.write_text(content, encoding="utf-8")
    return config_path


def workspace_git_env(workspace_path: str | Path, base_env: dict[str, str] | None = None) -> dict[str, str]:
    env = dict(base_env or os.environ.copy())
    env["GIT_CONFIG_GLOBAL"] = str(ensure_workspace_git_config(workspace_path, env=env))
    return env
