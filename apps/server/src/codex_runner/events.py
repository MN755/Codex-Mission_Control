from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class RunnerEvent:
    type: str
    payload: dict
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


def parse_json_line(line: str) -> dict | None:
    line = line.strip()
    if not line:
        return None
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        return {"type": "raw.output", "text": line}

