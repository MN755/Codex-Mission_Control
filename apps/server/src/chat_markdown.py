from __future__ import annotations

import re
from typing import Iterable


_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")


def compact_text(value: str | None, *, fallback: str = "Unknown") -> str:
    text = " ".join(str(value or "").strip().split())
    return text or fallback


def compact_reason(value: str | None, *, max_sentences: int = 2, max_chars: int = 260) -> str:
    text = compact_text(value, fallback="")
    if not text:
        return ""
    pieces = [piece.strip() for piece in _SENTENCE_BOUNDARY.split(text) if piece.strip()]
    if pieces:
        limited = " ".join(pieces[:max_sentences]).strip()
    else:
        limited = text
    if len(limited) <= max_chars:
        return limited
    return limited[: max_chars - 3].rstrip() + "..."


def bullet_lines(items: Iterable[str], *, empty_message: str) -> list[str]:
    normalized = [compact_text(item, fallback="").strip() for item in items if compact_text(item, fallback="").strip()]
    if not normalized:
        return [f"- {empty_message}"]
    return [f"- {item}" for item in normalized]


def option_lines(options: Iterable[dict], *, empty_message: str = "No options available.") -> list[str]:
    rows: list[str] = []
    for option in options:
        option_id = compact_text(str(option.get("id") or option.get("label") or "option"))
        label = compact_text(str(option.get("label") or option_id))
        description = compact_text(str(option.get("description") or ""), fallback="").strip()
        if description:
            rows.append(f"- `{option_id}`: {label} - {description}")
        else:
            rows.append(f"- `{option_id}`: {label}")
    return rows or [f"- {empty_message}"]


def section(title: str, lines: Iterable[str], *, empty_message: str | None = None) -> list[str]:
    body = [str(line).rstrip() for line in lines if str(line).strip()]
    if not body and empty_message is not None:
        body = [f"- {empty_message}"]
    return ["", f"### {title}", *body]


def join_markdown(lines: Iterable[str]) -> str:
    rendered = "\n".join(lines).strip()
    rendered = re.sub(r"\n{3,}", "\n\n", rendered)
    return rendered + "\n"
