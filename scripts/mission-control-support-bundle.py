from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVER_SRC = ROOT / "apps" / "server" / "src"
if str(SERVER_SRC) not in sys.path:
    sys.path.insert(0, str(SERVER_SRC))

from app_profile import get_or_create_app_profile  # noqa: E402
from db import SessionLocal, init_db  # noqa: E402
from startup import startup_service  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a redacted Mission Control diagnostic support bundle.")
    parser.add_argument("--json", action="store_true", help="Print the generated report payload as JSON.")
    args = parser.parse_args()

    init_db()
    session = SessionLocal()
    try:
        get_or_create_app_profile(session)
        report = startup_service.run_diagnostics(session)
    finally:
        session.close()

    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print("Mission Control support bundle generated.")
        print(f"Summary: {report.get('summary')}")
        print(f"Markdown report: {report.get('path')}")
        if report.get("json_path"):
            print(f"JSON report: {report.get('json_path')}")
        if report.get("bundle_path"):
            print(f"Bundle archive: {report.get('bundle_path')}")
        platform_profile = report.get("platform_profile") or {}
        if platform_profile:
            print(
                "Device: "
                f"{platform_profile.get('platform_label')} / "
                f"{platform_profile.get('architecture')} / "
                f"{platform_profile.get('cpu_count')} CPU(s)"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
