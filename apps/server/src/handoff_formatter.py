from __future__ import annotations

from chat_markdown import bullet_lines, join_markdown, section


def build_handoff_markdown(
    *,
    title: str,
    handoff_status: str,
    confidence_level: str,
    evidence_level: str,
    what_changed: list[str],
    how_to_run: list[str],
    validation_items: list[str],
    known_limitations: list[str],
    next_tasks: list[str],
    important_files: list[str],
    missing_evidence: list[str],
    dry_run: bool,
) -> str:
    status_label = handoff_status
    if dry_run:
        status_label += " (dry-run)"
    review_state = "Review required" if handoff_status == "needs_review" or missing_evidence else "No extra review gate recorded"
    evidence_state = "Verified" if evidence_level in {"high", "complete", "verified"} and not missing_evidence else "Partial / claimed"

    lines = [
        f"## {title}",
        "",
        f"**Status:** {status_label}",
        f"**Confidence / evidence:** {confidence_level} / {evidence_level}",
        f"**Evidence state:** {evidence_state}",
        f"**Review state:** {review_state}",
    ]
    if dry_run:
        lines.append("**Dry-run:** This summary is based on simulated execution and recorded dry-run evidence only.")

    lines.extend(section("What changed", bullet_lines(what_changed, empty_message="No detailed change list was recorded.")))
    lines.extend(section("How to run", bullet_lines(how_to_run, empty_message="No run instructions were recorded.")))
    lines.extend(
        section(
            "Validation / evidence",
            bullet_lines(validation_items, empty_message="Not run."),
        )
    )
    if missing_evidence:
        lines.extend(section("Needs review before trust", bullet_lines(missing_evidence, empty_message="No evidence warnings.")))
    lines.extend(
        section(
            "Known limitations",
            bullet_lines(known_limitations, empty_message="No limitations were recorded."),
        )
    )
    lines.extend(
        section(
            "Next recommended tasks",
            bullet_lines(next_tasks, empty_message="No explicit follow-up tasks were recorded."),
        )
    )
    lines.extend(
        section(
            "Important files / artifacts",
            bullet_lines(important_files, empty_message="No artifact paths were recorded."),
        )
    )
    return join_markdown(lines)
