from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Iterable


class PathValidationError(ValueError):
    pass


def _clean_path_text(raw_path: str | Path) -> str:
    text = str(raw_path).strip()
    if not text:
        raise PathValidationError("Path is required.")
    lowered = text.lower()
    if lowered.startswith(("http://", "https://", "ftp://", "file://")):
        raise PathValidationError("Only local filesystem paths are allowed.")
    if text.startswith(("\\\\", "//")):
        raise PathValidationError("Network paths are not allowed.")
    return text


def resolve_local_path(raw_path: str | Path, *, must_exist: bool = False, must_be_dir: bool = False) -> Path:
    candidate = Path(_clean_path_text(raw_path)).expanduser()
    resolved = candidate.resolve(strict=False)
    if not resolved.is_absolute():
        raise PathValidationError("Path must resolve to an absolute local filesystem path.")
    if str(resolved).startswith(("\\\\", "//")):
        raise PathValidationError("Network paths are not allowed.")
    if must_exist and not resolved.exists():
        raise PathValidationError("Path does not exist.")
    if must_be_dir and resolved.exists() and not resolved.is_dir():
        raise PathValidationError("Path must be a directory.")
    return resolved


def normalize_relative_subpath(raw_path: str | Path) -> Path:
    text = _clean_path_text(raw_path).replace("\\", "/")
    pure = PurePosixPath(text)
    if pure.is_absolute():
        raise PathValidationError("Target paths must be relative.")
    parts = [part for part in pure.parts if part not in {"", "."}]
    if not parts:
        raise PathValidationError("Target path must not be empty.")
    if any(part == ".." for part in parts):
        raise PathValidationError("Target paths must stay inside the selected root.")
    if ":" in parts[0]:
        raise PathValidationError("Drive-qualified target paths are not allowed.")
    return Path(*parts)


def resolve_relative_to_root(root: Path, raw_path: str | Path, *, must_exist: bool = False) -> Path:
    resolved_root = resolve_local_path(root, must_exist=True)
    relative = normalize_relative_subpath(raw_path)
    candidate = (resolved_root / relative).resolve(strict=False)
    try:
        candidate.relative_to(resolved_root)
    except ValueError as exc:
        raise PathValidationError("Target paths must stay inside the selected root.") from exc
    if must_exist and not candidate.exists():
        raise PathValidationError("Target path does not exist.")
    return candidate


def ensure_within_roots(path: str | Path, allowed_roots: Iterable[str | Path], *, must_exist: bool = False) -> Path:
    resolved = resolve_local_path(path, must_exist=must_exist)
    for root in allowed_roots:
        allowed = resolve_local_path(root, must_exist=True)
        try:
            resolved.relative_to(allowed)
            return resolved
        except ValueError:
            continue
    raise PathValidationError("Path is outside the allowed locations.")
