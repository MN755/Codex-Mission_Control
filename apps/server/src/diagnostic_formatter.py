from __future__ import annotations

from chat_markdown import bullet_lines, join_markdown, section


def build_diagnostic_summary_markdown(
    *,
    status: str,
    what_works: list[str],
    needs_attention: list[str],
    recommended_fixes: list[str],
    safe_commands: list[str],
    notes: list[str],
) -> str:
    lines = [
        "## Mission Control Diagnostics",
        "",
        f"**Status:** {status}",
        "**Dashboard:** optional",
    ]
    lines.extend(section("What works", bullet_lines(what_works, empty_message="No healthy checks were recorded.")))
    lines.extend(
        section(
            "What needs attention",
            bullet_lines(needs_attention, empty_message="No degraded or broken checks are recorded."),
        )
    )
    lines.extend(
        section(
            "Recommended fixes",
            bullet_lines(recommended_fixes, empty_message="No fixes are recommended right now."),
        )
    )
    lines.extend(
        section(
            "Safe commands",
            [f"- `{command}`" for command in safe_commands if str(command).strip()],
            empty_message="No extra troubleshooting commands are needed right now.",
        )
    )
    if notes:
        lines.extend(section("Notes", bullet_lines(notes, empty_message="No extra notes.")))
    return join_markdown(lines)
