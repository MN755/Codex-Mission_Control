from __future__ import annotations

from collections import OrderedDict

from chat_markdown import join_markdown, section


EVENT_DIGEST_CATEGORY_ORDER = [
    "Manager",
    "Agents",
    "Approvals",
    "Validation",
    "Handoff",
    "Conflicts",
    "Recovery",
    "Diagnostics",
]


def _collapse_items(items: list[str], *, max_items: int = 5) -> list[str]:
    counts: OrderedDict[str, int] = OrderedDict()
    for item in items:
        normalized = " ".join(str(item).strip().split())
        if not normalized:
            continue
        counts[normalized] = counts.get(normalized, 0) + 1
    lines: list[str] = []
    for text, count in counts.items():
        lines.append(f"- {text} (x{count})" if count > 1 else f"- {text}")
        if len(lines) >= max_items:
            break
    return lines


def build_event_digest_markdown(*, title: str, grouped_items: dict[str, list[str]]) -> str:
    lines = [f"## {title}"]
    ordered_keys = [key for key in EVENT_DIGEST_CATEGORY_ORDER if grouped_items.get(key)] + [
        key for key in grouped_items.keys() if key not in EVENT_DIGEST_CATEGORY_ORDER and grouped_items.get(key)
    ]
    if not ordered_keys:
        lines.extend(["", "No significant orchestration events were recorded in this window."])
        return join_markdown(lines)
    for key in ordered_keys:
        lines.extend(section(key, _collapse_items(grouped_items.get(key, [])), empty_message="No notable events."))
    return join_markdown(lines)
