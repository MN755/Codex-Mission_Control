from __future__ import annotations

import re
import textwrap
from typing import Any

from models import utc_now

DEFAULT_ASCII_MONITOR_WIDTH = 120


def _display_trim(text: str, width: int) -> str:
    compact = " ".join(str(text or "").split())
    if width <= 3:
        return compact[:width]
    if len(compact) <= width:
        return compact
    return compact[: width - 3] + "..."


def _display_wrap(prefix: str, text: str, width: int) -> list[str]:
    content = " ".join(str(text or "").split())
    if not content:
        return [prefix.rstrip()]
    available = max(10, width - len(prefix))
    wrapped = textwrap.wrap(content, width=available, break_long_words=True, break_on_hyphens=False) or [content]
    lines = [prefix + wrapped[0]]
    indent = " " * len(prefix)
    lines.extend(indent + item for item in wrapped[1:])
    return lines


def _display_section(title: str, lines: list[str], width: int) -> list[str]:
    output = [f"[ {title} ]"]
    if not lines:
        output.append("  (no data)")
    else:
        for line in lines:
            output.extend(_display_wrap("  ", line, width))
    output.append("")
    return output


def _display_visible_len(text: str) -> int:
    return len(re.sub(r"\x1b\[[0-9;]*m", "", str(text or "")))


def _display_pad_visible(text: str, width: int) -> str:
    visible = _display_visible_len(text)
    if visible >= width:
        return text
    return text + (" " * (width - visible))


def _display_join_columns(left: list[str], right: list[str], width: int, *, gap: int = 4) -> list[str]:
    if not right:
        return left
    right_width = max(_display_visible_len(line) for line in right)
    right_width = max(16, min(right_width, width // 2))
    left_width = width - right_width - gap
    if left_width < 32:
        return left + [""] + right
    row_count = max(len(left), len(right))
    left_rows = left + [""] * (row_count - len(left))
    right_rows = right + [""] * (row_count - len(right))
    merged: list[str] = []
    for left_row, right_row in zip(left_rows, right_rows):
        merged.append(_display_pad_visible(_display_trim(left_row, left_width), left_width) + (" " * gap) + right_row)
    return merged


def _status_badge(status: str | None) -> str:
    label = str(status or "unknown").strip() or "unknown"
    return label.upper()


def _mission_control_logo_lines() -> list[str]:
    return [
        r" __  __  ____ ",
        r"|  \/  |/ ___|",
        r"| |\/| | |    ",
        r"| |  | | |___ ",
        r"|_|  |_|\____|",
        r"MISSION CONTROL",
    ]


def _display_card_lines(title: str, lines: list[str], width: int) -> list[str]:
    inner_width = max(24, width - 4)
    border = "+" + ("-" * (inner_width + 2)) + "+"
    title_text = f" {title} "
    title_visible = min(len(title_text), inner_width)
    title_line = "|" + title_text[:title_visible].ljust(inner_width + 2, "-") + "|"
    output = [border, title_line]
    content_lines = lines or ["(no data)"]
    for content in content_lines:
        compact = " ".join(str(content or "").split())
        wrapped = textwrap.wrap(compact, width=inner_width, break_long_words=True, break_on_hyphens=False) or [""]
        for wrapped_line in wrapped:
            output.append("| " + _display_pad_visible(wrapped_line, inner_width) + " |")
    output.append(border)
    return output


def _event_preview_display(event: dict[str, Any]) -> str:
    getter = event.get if isinstance(event, dict) else lambda key, default=None: getattr(event, key, default)
    event_id = getter("id")
    event_type = str(getter("event_type") or getter("type") or "event")
    payload_json = getter("payload_json")
    payload = payload_json if isinstance(payload_json, dict) else getter("payload")
    payload = payload if isinstance(payload, dict) else {}
    summary = str(
        getter("summary")
        or payload.get("summary")
        or payload.get("message")
        or payload.get("title")
        or event_type
    ).strip()
    if summary == event_type:
        return f"#{event_id} {event_type}"
    return f"#{event_id} {summary}"


def _manager_focus_lines(payload: dict[str, Any]) -> list[str]:
    status_payload = dict(payload.get("status_payload") or {})
    status_summary = dict(payload.get("status_summary") or {})
    machine_payload = dict(status_summary.get("machine_payload_json") or {})
    lines: list[str] = []
    manager_status = str(status_payload.get("manager_status") or payload.get("manager_status") or "").strip()
    if manager_status:
        lines.append(f"Status: {manager_status}")
    next_step = str(machine_payload.get("next_expected_step") or status_payload.get("next_expected_action") or "").strip()
    if next_step:
        lines.append(f"Next: {next_step}")
    for item in list(machine_payload.get("current_work") or [])[:4]:
        compact = " ".join(str(item or "").split())
        if compact:
            lines.append(f"Focus: {compact}")
    blockers = list(machine_payload.get("current_blockers") or status_payload.get("current_blockers") or [])[:2]
    for blocker in blockers:
        compact = " ".join(str(blocker or "").split())
        if compact:
            lines.append(f"Blocker: {compact}")
    return lines


def _agent_focus(agent: dict[str, Any]) -> str:
    return str(
        agent.get("current_action")
        or agent.get("current_task_title")
        or agent.get("mission")
        or agent.get("status")
        or "No active focus recorded."
    )


def _manager_card_lines(payload: dict[str, Any], manager: dict[str, Any]) -> list[str]:
    name = str(manager.get("name") or "Mission Control Manager")
    runner = str(manager.get("runner_type") or "unknown")
    model = str(manager.get("active_model") or "unknown")
    status = str(manager.get("status") or "unknown")
    lines = [
        f"Manager: {name}",
        f"Runner: {runner} | Model: {model} | Status: {_status_badge(status)}",
    ]
    lines.extend(_manager_focus_lines(payload)[:5])
    return lines


def _agent_card_lines(agent: dict[str, Any]) -> list[str]:
    name = str(agent.get("name") or f"Agent {agent.get('id') or '?'}")
    runner = str(agent.get("runner_type") or "unknown")
    model = str(agent.get("active_model") or "unknown")
    status = str(agent.get("status") or "unknown")
    lines = [
        f"Agent: {name}",
        f"Runner: {runner} | Model: {model} | Status: {_status_badge(status)}",
    ]
    task_title = str(agent.get("current_task_title") or "").strip()
    if task_title:
        lines.append(f"Current task: {task_title}")
    lines.append(f"Focus: {_agent_focus(agent)}")
    mission = str(agent.get("mission") or "").strip()
    if mission and mission.lower() not in str(_agent_focus(agent)).lower():
        lines.append(f"Mission: {mission}")
    return lines


def build_ascii_monitor_frame(payload: dict[str, Any], *, width: int = DEFAULT_ASCII_MONITOR_WIDTH) -> str:
    status_payload = dict(payload.get("status_payload") or {})
    manager = dict(payload.get("manager") or status_payload.get("manager") or {})
    status_summary = dict(payload.get("status_summary") or {})
    handoff_summary = dict(payload.get("handoff_summary") or {})
    handoff_machine = dict(handoff_summary.get("machine_payload_json") or {})
    pending = list(payload.get("pending_decisions") or [])
    active_agents = list(status_payload.get("active_agents") or [])
    events = list(payload.get("events") or [])
    warnings = list(payload.get("warnings") or [])
    current_status = str(status_payload.get("orchestration_status") or payload.get("status") or "unknown")
    handoff_status = str(handoff_machine.get("status") or "unknown")
    checked_at = str(payload.get("checked_at") or utc_now().isoformat())

    render_summary = (
        f"Updated: {checked_at} | Status: {current_status.upper()} | Pending decisions: {len(pending)} | "
        f"Active agents: {len(active_agents)} | Handoff: {handoff_status.upper()}"
    )
    header_left = [
        "MISSION CONTROL LIVE",
        f"Project: {payload.get('project_name') or payload.get('project_id')}",
        f"Orchestration: {payload.get('orchestration_id') or 'none'} | Status: {current_status.upper()}",
        f"Pending decisions: {len(pending)} | Active agents: {len(active_agents)} | Handoff: {handoff_status.upper()}",
        f"Updated: {checked_at}",
        f"Workspace: {payload.get('workspace_path') or 'n/a'}",
        f"Event window: {payload.get('event_window') or 'last_15_minutes'}",
    ]

    lines = ["=" * width]
    lines.extend(_display_join_columns(header_left, _mission_control_logo_lines(), width))
    lines.extend(["=" * width, _display_trim(render_summary, width), "", "[ Manager ]"])
    lines.extend(_display_card_lines("Manager Bridge", _manager_card_lines(payload, manager), width))
    lines.append("")

    lines.append("[ Agents ]")
    if not active_agents:
        lines.extend(_display_card_lines("Agent Lane", ["No active worker agents were returned."], width))
    else:
        for agent in active_agents[:8]:
            agent_title = str(agent.get("name") or f"Agent {agent.get('id') or '?'}")
            lines.extend(_display_card_lines(agent_title, _agent_card_lines(agent), width))
            lines.append("")

    event_lines = [_event_preview_display(event) for event in events[-6:]] or ["No recent orchestration events were returned."]
    lines.extend(_display_section("Event Pulse", event_lines, width))

    meta_lines = [
        f"Repeat command: {payload.get('recommended_command') or 'python scripts/mission-control-manage.py orchestration-display'}",
        f"Snapshot file: {payload.get('snapshot_path') if payload.get('snapshot_saved') else 'not saved'}",
        f"Browser refresh cadence: {float(payload.get('refresh_seconds') or 1.0):0.1f}s",
    ]
    for warning in warnings[:3]:
        meta_lines.append(f"Warning: {warning}")
    lines.extend(_display_section("Runtime Notes", meta_lines, width))
    lines.append(_display_trim("Browser ASCII monitor is mirroring the live orchestration state.", width))
    return "\n".join(lines)
