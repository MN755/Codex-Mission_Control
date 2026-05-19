from __future__ import annotations

import re


ERROR_CODE_PATTERN = re.compile(r"^MC-[A-Z]+(?:-[A-Z0-9]+)+-\d{3}$")


def is_valid_error_code(code: str) -> bool:
    return bool(ERROR_CODE_PATTERN.match(str(code or "").strip()))


def docs_anchor_for_code(code: str) -> str:
    return code.strip().lower()
