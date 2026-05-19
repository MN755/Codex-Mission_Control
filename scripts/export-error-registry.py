from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVER_SRC = ROOT / "apps" / "server" / "src"
OUTPUT = ROOT / "docs" / "ERROR_REGISTRY.md"

if str(SERVER_SRC) not in sys.path:
    sys.path.insert(0, str(SERVER_SRC))

from errors.registry import iter_error_definitions  # noqa: E402


def _docs_link(code: str, anchor: str) -> str:
    return f"[{code}](https://github.com/MN755/Codex-Mission_Control/wiki/Errors-and-Debug-Codes#{anchor})"


def build_registry_markdown() -> str:
    definitions = list(iter_error_definitions())
    lines = [
        "# Mission Control Error Registry",
        "",
        "> Status: Reference",
        "",
        "This file is generated from `apps/server/src/errors/registry.py`. Do not edit it by hand.",
        "",
        f"Total codes: `{len(definitions)}`",
        "",
        "| Code | Title | Family | Severity | Breakpoint | Retryable | User action required | HTTP |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for item in definitions:
        lines.append(
            f"| {_docs_link(item.code, item.docs_anchor)} | {item.title} | `{item.family}` | `{item.severity}` | "
            f"`{item.default_breakpoint}` | {'Yes' if item.retryable else 'No'} | "
            f"{'Yes' if item.user_action_required else 'No'} | `{item.http_status}` |"
        )
    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- The code is the stable identifier. User-facing wording may change.",
            "- Search the code in logs, tests, diagnostics, or the wiki first.",
            "- See [Mission Control Errors](ERRORS.md) for the error shape and family overview.",
        ]
    )
    return "\n".join(lines) + "\n"


def main(argv: list[str]) -> int:
    markdown = build_registry_markdown()
    if "--check" in argv:
        if not OUTPUT.exists() or OUTPUT.read_text(encoding="utf-8") != markdown:
            print("Error registry export is out of date.")
            return 1
        print("Error registry export is current.")
        return 0
    OUTPUT.write_text(markdown, encoding="utf-8")
    print(f"Wrote {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
