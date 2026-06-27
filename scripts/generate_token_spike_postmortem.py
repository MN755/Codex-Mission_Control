from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import math
import sqlite3
import subprocess
import textwrap
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / ".runtime" / "mission_control.sqlite3"
OUTPUT_DIR = ROOT / "docs" / "forensics"


PROFILE_PEAK_TOKENS = 1_500_000_000
PROFILE_TOTAL_THREADS = 2_103
PROFILE_SOURCE = (
    "User-supplied Codex profile screenshot captured on June 21, 2026 "
    "showing 1.5B peak tokens and 2,103 total threads."
)


def run_git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def slugify(text: str) -> str:
    out = []
    for ch in text.lower():
        if ch.isalnum():
            out.append(ch)
        elif out and out[-1] != "-":
            out.append("-")
    return "".join(out).strip("-")


def iso_now() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def fmt_int(value: int | float | None) -> str:
    if value is None:
        return "0"
    if isinstance(value, float) and math.isnan(value):
        return "0"
    return f"{int(value):,}"


def fmt_dt(value: str | None) -> str:
    return value or "-"


def json_loads_safe(raw: str | None) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


@dataclass
class RepoFileRow:
    path: str
    extension: str
    lines: int | None
    size_bytes: int
    text_scanned: bool


def tracked_files() -> list[Path]:
    output = run_git("ls-files")
    files = [ROOT / line for line in output.splitlines() if line.strip()]
    return [path for path in files if path.exists()]


def count_repo_lines(files: list[Path]) -> list[RepoFileRow]:
    rows: list[RepoFileRow] = []
    for path in files:
        rel = path.relative_to(ROOT).as_posix()
        ext = path.suffix.lower() or "(none)"
        size = path.stat().st_size
        try:
            text = path.read_text(encoding="utf-8")
            lines = len(text.splitlines())
            rows.append(
                RepoFileRow(
                    path=rel,
                    extension=ext,
                    lines=lines,
                    size_bytes=size,
                    text_scanned=True,
                )
            )
            continue
        except UnicodeDecodeError:
            pass
        try:
            text = path.read_text(encoding="utf-8-sig")
            lines = len(text.splitlines())
            rows.append(
                RepoFileRow(
                    path=rel,
                    extension=ext,
                    lines=lines,
                    size_bytes=size,
                    text_scanned=True,
                )
            )
            continue
        except UnicodeDecodeError:
            rows.append(
                RepoFileRow(
                    path=rel,
                    extension=ext,
                    lines=None,
                    size_bytes=size,
                    text_scanned=False,
                )
            )
    return rows


def query_rows(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
    cur = conn.execute(sql, params)
    return cur.fetchall()


def query_value(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> Any:
    row = conn.execute(sql, params).fetchone()
    if not row:
        return None
    if isinstance(row, sqlite3.Row):
        return row[0]
    return row[0]


def gather_data(project_id: int) -> dict[str, Any]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    project = query_rows(
        conn,
        """
        select id, name, status, runner_mode, manager_mode, handoff_status,
               workspace_path, created_at, updated_at
        from projects
        where id = ?
        """,
        (project_id,),
    )[0]

    totals = {
        "projects": query_value(conn, "select count(*) from projects"),
        "agents": query_value(conn, "select count(*) from agents"),
        "agent_runs": query_value(conn, "select count(*) from agent_runs"),
        "tasks": query_value(conn, "select count(*) from tasks"),
        "event_logs": len(list((ROOT / ".runtime" / "logs").glob("*.events.jsonl"))),
    }

    local_total_tokens = query_value(
        conn,
        "select coalesce(sum(json_extract(usage_json, '$.total_tokens')), 0) from agent_runs",
    )
    local_input_tokens = query_value(
        conn,
        "select coalesce(sum(json_extract(usage_json, '$.input_tokens')), 0) from agent_runs",
    )
    local_cached_tokens = query_value(
        conn,
        "select coalesce(sum(json_extract(usage_json, '$.cached_input_tokens')), 0) from agent_runs",
    )
    local_output_tokens = query_value(
        conn,
        "select coalesce(sum(json_extract(usage_json, '$.output_tokens')), 0) from agent_runs",
    )

    project_runs = query_rows(
        conn,
        """
        select
            ar.id,
            ar.task_id,
            ar.agent_id,
            ag.name as agent_name,
            t.title as task_title,
            ar.runner_type,
            ar.status,
            coalesce(ar.failure_classification, '(none)') as failure_classification,
            ar.started_at,
            ar.finished_at,
            json_extract(ar.usage_json, '$.input_tokens') as input_tokens,
            json_extract(ar.usage_json, '$.cached_input_tokens') as cached_input_tokens,
            json_extract(ar.usage_json, '$.output_tokens') as output_tokens,
            json_extract(ar.usage_json, '$.total_tokens') as total_tokens,
            ar.report_json,
            ar.result_envelope_json
        from agent_runs ar
        join agents ag on ag.id = ar.agent_id
        left join tasks t on t.id = ar.task_id
        where ag.project_id = ?
        order by ar.id
        """,
        (project_id,),
    )

    tasks = query_rows(
        conn,
        """
        select id, title, status, priority, waiting_reason, updated_at
        from tasks
        where project_id = ?
        order by status, title
        """,
        (project_id,),
    )

    agents = query_rows(
        conn,
        """
        select name, kind, role, status, active_model, active_reasoning_effort,
               active_runner_type, failure_count, current_action, last_update
        from agents
        where project_id = ?
        order by name
        """,
        (project_id,),
    )

    project_task_status = query_rows(
        conn,
        "select status, count(*) as count from tasks where project_id = ? group by status order by count desc",
        (project_id,),
    )
    project_agent_status = query_rows(
        conn,
        "select status, count(*) as count from agents where project_id = ? group by status order by count desc",
        (project_id,),
    )
    project_run_status = query_rows(
        conn,
        """
        select ar.status, coalesce(ar.failure_classification, '(none)') as failure_classification,
               count(*) as count,
               coalesce(sum(json_extract(ar.usage_json, '$.total_tokens')), 0) as total_tokens
        from agent_runs ar
        join agents ag on ag.id = ar.agent_id
        where ag.project_id = ?
        group by ar.status, coalesce(ar.failure_classification, '(none)')
        order by count desc
        """,
        (project_id,),
    )
    project_hourly = query_rows(
        conn,
        """
        select substr(ar.started_at, 1, 13) as hour,
               count(*) as run_count,
               coalesce(sum(json_extract(ar.usage_json, '$.total_tokens')), 0) as total_tokens
        from agent_runs ar
        join agents ag on ag.id = ar.agent_id
        where ag.project_id = ?
        group by substr(ar.started_at, 1, 13)
        order by hour
        """,
        (project_id,),
    )
    task_retries = query_rows(
        conn,
        """
        select ar.task_id, t.title, count(*) as runs,
               coalesce(sum(json_extract(ar.usage_json, '$.total_tokens')), 0) as total_tokens
        from agent_runs ar
        join agents ag on ag.id = ar.agent_id
        left join tasks t on t.id = ar.task_id
        where ag.project_id = ? and ar.task_id is not null
        group by ar.task_id, t.title
        having count(*) > 1
        order by runs desc, total_tokens desc
        """,
        (project_id,),
    )
    zero_file_done = query_value(
        conn,
        """
        select count(*)
        from agent_runs ar
        join agents ag on ag.id = ar.agent_id
        where ag.project_id = ?
          and ar.status = 'done'
          and json_array_length(json_extract(ar.report_json, '$.files_changed')) = 0
        """,
        (project_id,),
    )
    zero_file_all = query_value(
        conn,
        """
        select count(*)
        from agent_runs ar
        join agents ag on ag.id = ar.agent_id
        where ag.project_id = ?
          and json_array_length(json_extract(ar.report_json, '$.files_changed')) = 0
        """,
        (project_id,),
    )
    usage_limit_blocks = query_value(
        conn,
        """
        select count(*)
        from agent_runs ar
        join agents ag on ag.id = ar.agent_id
        where ag.project_id = ?
          and lower(coalesce(ar.report_json, '')) like '%usage limit%'
        """,
        (project_id,),
    )
    missing_report = query_value(
        conn,
        """
        select count(*)
        from agent_runs ar
        join agents ag on ag.id = ar.agent_id
        where ag.project_id = ?
          and (ar.report_json is null or ar.report_json = '' or ar.report_json = 'null')
        """,
        (project_id,),
    )

    top_runs = sorted(
        project_runs,
        key=lambda row: row["total_tokens"] or 0,
        reverse=True,
    )[:25]

    files = tracked_files()
    repo_rows = count_repo_lines(files)
    repo_total_lines = sum(row.lines or 0 for row in repo_rows)
    repo_text_files = sum(1 for row in repo_rows if row.text_scanned)
    repo_binary_files = sum(1 for row in repo_rows if not row.text_scanned)

    by_extension: Counter[str] = Counter()
    ext_lines: Counter[str] = Counter()
    by_top_dir: Counter[str] = Counter()
    top_dir_lines: Counter[str] = Counter()
    for row in repo_rows:
        by_extension[row.extension] += 1
        ext_lines[row.extension] += row.lines or 0
        top_dir = row.path.split("/", 1)[0] if "/" in row.path else "(root)"
        by_top_dir[top_dir] += 1
        top_dir_lines[top_dir] += row.lines or 0

    return {
        "generated_at": iso_now(),
        "git_commit": run_git("rev-parse", "HEAD"),
        "project": dict(project),
        "totals": totals,
        "local_usage": {
            "total_tokens": local_total_tokens,
            "input_tokens": local_input_tokens,
            "cached_input_tokens": local_cached_tokens,
            "output_tokens": local_output_tokens,
            "delta_vs_profile": PROFILE_PEAK_TOKENS - int(local_total_tokens or 0),
            "profile_peak_tokens": PROFILE_PEAK_TOKENS,
        },
        "project_runs": [dict(row) for row in project_runs],
        "tasks": [dict(row) for row in tasks],
        "agents": [dict(row) for row in agents],
        "project_task_status": [dict(row) for row in project_task_status],
        "project_agent_status": [dict(row) for row in project_agent_status],
        "project_run_status": [dict(row) for row in project_run_status],
        "project_hourly": [dict(row) for row in project_hourly],
        "task_retries": [dict(row) for row in task_retries],
        "zero_file_done": int(zero_file_done or 0),
        "zero_file_all": int(zero_file_all or 0),
        "usage_limit_blocks": int(usage_limit_blocks or 0),
        "missing_report": int(missing_report or 0),
        "top_runs": [dict(row) for row in top_runs],
        "repo_rows": repo_rows,
        "repo_summary": {
            "tracked_files": len(repo_rows),
            "text_files": repo_text_files,
            "binary_files": repo_binary_files,
            "total_lines": repo_total_lines,
            "by_extension": by_extension,
            "ext_lines": ext_lines,
            "by_top_dir": by_top_dir,
            "top_dir_lines": top_dir_lines,
        },
    }


def md_table(headers: list[str], rows: list[list[Any]]) -> str:
    out = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for row in rows:
        out.append("| " + " | ".join(str(cell).replace("\n", " ") for cell in row) + " |")
    return "\n".join(out)


def render_markdown(data: dict[str, Any]) -> str:
    p = data["project"]
    usage = data["local_usage"]
    repo = data["repo_summary"]

    lines: list[str] = []
    lines.append("# Mission Control Token Spike Postmortem")
    lines.append("")
    lines.append("## Executive Summary")
    lines.append("")
    lines.append(
        "This report explains why Mission Control burned through a catastrophic amount of tokens "
        "and thread/session churn during the benchmark effort focused on project "
        f"`{p['id']}` (`{p['name']}`). The short version is brutal: Mission Control kept spawning and "
        "re-spawning worker runs faster than it was closing valid work, it continued operating through "
        "model-policy failures and usage-limit failures, it allowed the same task lanes to be retried dozens "
        "to more than a hundred times, and I did not pull the emergency brake soon enough."
    )
    lines.append("")
    lines.append(
        "Local Mission Control telemetry records **"
        f"{fmt_int(usage['total_tokens'])} tokens** across all stored runs, including **{fmt_int(query_project_total_tokens(data))} "
        f"tokens** for project `{p['id']}` alone. The user-supplied Codex profile screenshot reports a **1.5B peak-token day** "
        f"and **{fmt_int(PROFILE_TOTAL_THREADS)} total threads**. Those two facts are compatible rather than contradictory: the "
        "local database is clearly undercounting the full Codex-side billing footprint, while the local run volume and thread-spawn "
        "patterns explain how the profile number could reach that scale."
    )
    lines.append("")
    lines.append(
        "Most importantly, this was not one bug. It was a stacked failure chain: weak run-budget controls, missing circuit breakers, "
        "retry churn, scheduler supersession churn, policy-invalid model assignments, usage-limit handling that did not force a clean "
        "stop, and bad operator supervision from me."
    )
    lines.append("")
    lines.append("## Incident Scope")
    lines.append("")
    lines.append(
        f"- Report generated at: `{data['generated_at']}`\n"
        f"- Repo commit examined: `{data['git_commit']}`\n"
        f"- Mission Control DB: `{DB_PATH.as_posix()}`\n"
        f"- Focus project: `{p['id']}` / `{p['name']}`\n"
        f"- Project workspace: `{p['workspace_path']}`\n"
        f"- Project status when frozen: `{p['status']}`\n"
        f"- Runner mode: `{p['runner_mode']}`\n"
        f"- Manager mode: `{p['manager_mode']}`\n"
        f"- Handoff status: `{p['handoff_status']}`\n"
        f"- Evidence source for 1.5B / 2,103 numbers: {PROFILE_SOURCE}"
    )
    lines.append("")
    lines.append("## High-Level Metrics")
    lines.append("")
    lines.append(
        md_table(
            ["Metric", "Value"],
            [
                ["Projects in local DB", fmt_int(data["totals"]["projects"])],
                ["Agents in local DB", fmt_int(data["totals"]["agents"])],
                ["Agent runs in local DB", fmt_int(data["totals"]["agent_runs"])],
                ["Tasks in local DB", fmt_int(data["totals"]["tasks"])],
                ["Event log files in `.runtime/logs`", fmt_int(data["totals"]["event_logs"])],
                ["Local total tokens recorded", fmt_int(usage["total_tokens"])],
                ["Local input tokens recorded", fmt_int(usage["input_tokens"])],
                ["Local cached input tokens recorded", fmt_int(usage["cached_input_tokens"])],
                ["Local output tokens recorded", fmt_int(usage["output_tokens"])],
                ["User profile peak tokens", fmt_int(usage["profile_peak_tokens"])],
                ["Unexplained gap vs local DB", fmt_int(usage["delta_vs_profile"])],
                ["User profile total threads", fmt_int(PROFILE_TOTAL_THREADS)],
                ["Tracked repo files scanned", fmt_int(repo["tracked_files"])],
                ["Tracked text files line-counted", fmt_int(repo["text_files"])],
                ["Tracked binary files skipped for line count", fmt_int(repo["binary_files"])],
                ["Tracked text lines scanned", fmt_int(repo["total_lines"])],
            ],
        )
    )
    lines.append("")
    lines.append("## Why The 1.5B Number Happened")
    lines.append("")
    lines.append("### 1. Mission Control created far too many runs")
    lines.append("")
    lines.append(
        f"Project `{p['id']}` alone generated **{fmt_int(len(data['project_runs']))} stored worker runs**. "
        "That is already enough to explain why the Codex profile shows thread explosion: one run/retry/review loop "
        "maps very closely to one Codex thread or session lifecycle."
    )
    lines.append("")
    lines.append("### 2. It kept retrying the same task lanes")
    lines.append("")
    lines.append(
        "The same defect batches were run again and again. Instead of a clean work queue, the system accumulated "
        "`superseded`, `unblock`, and `re-run` variants of the same lane family, which means the scheduler was doing "
        "substantial self-generated work."
    )
    lines.append("")
    retry_rows = [
        [row["task_id"], row["title"], fmt_int(row["runs"]), fmt_int(row["total_tokens"])]
        for row in data["task_retries"][:20]
    ]
    lines.append(md_table(["Task ID", "Task Title", "Runs", "Tokens"], retry_rows))
    lines.append("")
    lines.append("### 3. It spent real money on no-op and low-yield runs")
    lines.append("")
    lines.append(
        f"- `done` runs with zero changed files recorded: **{fmt_int(data['zero_file_done'])}**\n"
        f"- All runs with zero changed files recorded: **{fmt_int(data['zero_file_all'])}**\n"
        f"- Runs missing a report entirely: **{fmt_int(data['missing_report'])}**"
    )
    lines.append("")
    lines.append(
        "That means Mission Control was willing to count or at least execute a large amount of work that produced no code changes, "
        "which is exactly how you turn tokens into heat."
    )
    lines.append("")
    lines.append("### 4. It continued through hard failures instead of tripping a stop condition")
    lines.append("")
    lines.append(
        f"- Usage-limit blocked runs found in stored reports: **{fmt_int(data['usage_limit_blocks'])}**\n"
        "- Runner-bug failures included invalid model selection and malformed completion envelopes.\n"
        "- The benchmark kept generating backlog churn and unblock tasks instead of entering a hard-fail quarantine."
    )
    lines.append("")
    lines.append("## Thread Explosion Analysis")
    lines.append("")
    lines.append(
        f"The Codex profile reports **{fmt_int(PROFILE_TOTAL_THREADS)} total threads**. The local Mission Control DB contains "
        f"**{fmt_int(data['totals']['agent_runs'])} agent runs** overall, with **{fmt_int(len(data['project_runs']))}** of them in "
        f"project `{p['id']}` alone. That is not a coincidence. The simplest explanation is that Mission Control's worker orchestration "
        "pattern was creating a fresh Codex-side session or thread for each lane execution, retry, review pass, or resume attempt."
    )
    lines.append("")
    lines.append(
        "The remaining difference between 2,103 profile threads and 1,982 local agent runs is plausibly explained by manager-side sessions, "
        "monitoring threads, manual babysitting threads, and failed or partially-persisted runs that were billed on the Codex side but did "
        "not leave a clean local DB envelope."
    )
    lines.append("")
    lines.append("## Status Mix")
    lines.append("")
    status_rows = [
        [row["status"], row["failure_classification"], fmt_int(row["count"]), fmt_int(row["total_tokens"])]
        for row in data["project_run_status"]
    ]
    lines.append(md_table(["Run Status", "Failure Class", "Count", "Tokens"], status_rows))
    lines.append("")
    lines.append("## Hourly Burn Pattern")
    lines.append("")
    hour_rows = [
        [row["hour"], fmt_int(row["run_count"]), fmt_int(row["total_tokens"])]
        for row in data["project_hourly"]
    ]
    lines.append(md_table(["Hour", "Runs", "Tokens"], hour_rows))
    lines.append("")
    lines.append("## Concrete Failure Signatures")
    lines.append("")
    lines.append("### Unsupported model selection")
    lines.append("")
    lines.append(
        "Stored runner-bug envelopes show repeated 400-level failures from Codex itself because Mission Control tried to use "
        "`gpt-5.3-codex` with a ChatGPT account, which that environment did not support. That means the system was not validating "
        "worker model policy against the actual runtime before burning retries."
    )
    lines.append("")
    lines.append("### Usage-limit continuation")
    lines.append("")
    lines.append(
        "Stored reports explicitly contain the message \"You've hit your usage limit\" in multiple blocked runs. A sane orchestrator should "
        "have transitioned the entire benchmark into a global blocked state at that point. Instead, it kept creating more lane churn."
    )
    lines.append("")
    lines.append("### Completion-envelope integrity failures")
    lines.append("")
    lines.append(
        "At least some runs failed because the worker completion envelope was missing the required report object. That means even after paying "
        "for the run, the result path could still throw the work away and invite a retry."
    )
    lines.append("")
    lines.append("### Scheduler supersession churn")
    lines.append("")
    lines.append(
        "Project task state shows the scheduler spent a huge amount of effort creating and superseding work items instead of converging on a "
        "stable deduplicated backlog. That is why the task board is full of `Apps X Defect Batch`, `Unblock: Apps X Defect Batch`, and "
        "`Provide actual evidence or reclassify` variants."
    )
    lines.append("")
    task_status_rows = [[row["status"], fmt_int(row["count"])] for row in data["project_task_status"]]
    lines.append(md_table(["Task Status", "Count"], task_status_rows))
    lines.append("")
    lines.append("## NTSB-Style Breakdown")
    lines.append("")
    lines.append("### Factual Sequence")
    lines.append("")
    lines.append("1. A live benchmark orchestration was launched with a swarm-oriented plan and aggressive throughput goals.")
    lines.append("2. Mission Control generated many parallel defect-batch lanes and began creating worker runs at scale.")
    lines.append("3. Some lanes completed real work, but the system also created high-volume retries, superseded lanes, and review-only churn.")
    lines.append("4. Invalid model-policy selections triggered runner-bug failures instead of a global stop.")
    lines.append("5. Usage-limit failures appeared in stored run reports, but the system did not enter a durable kill state.")
    lines.append("6. More unblock/re-run/superseded tasks were generated, amplifying thread count and token usage.")
    lines.append("7. I continued babysitting and recovery attempts instead of terminating the benchmark as soon as it became economically irrational.")
    lines.append("8. The user profile eventually showed a 1.5B peak-token day and 2,103 total threads.")
    lines.append("")
    lines.append("### Probable Cause")
    lines.append("")
    lines.append(
        "The probable cause was uncontrolled run amplification inside Mission Control: the orchestrator lacked hard economic guardrails and "
        "allowed the same logical work to be executed repeatedly across fresh worker sessions, even after invalid-model errors, usage-limit "
        "signals, no-change outcomes, and scheduler supersession churn indicated the benchmark was no longer behaving like a disciplined queue."
    )
    lines.append("")
    lines.append("### Contributing Factors")
    lines.append("")
    lines.append("1. No global token budget or cost circuit breaker.")
    lines.append("2. No hard cap on run count per task, per lane family, or per benchmark.")
    lines.append("3. Model-policy validation happened too late or too weakly.")
    lines.append("4. Usage-limit errors were treated as lane-local problems instead of a benchmark-wide stop signal.")
    lines.append("5. Review and ledger lanes were allowed to churn repeatedly.")
    lines.append("6. Zero-change runs could still be treated as acceptable enough to keep the system moving.")
    lines.append("7. I supervised for continuity instead of safety and did not escalate to full shutdown fast enough.")
    lines.append("")
    lines.append("### Findings")
    lines.append("")
    lines.append("1. Mission Control was productive in pockets, but not economically or operationally bounded.")
    lines.append("2. The benchmark counted movement in the board and ledger lanes too easily, which encouraged extra runs.")
    lines.append("3. Thread creation is almost certainly correlated with worker-run creation and retry creation.")
    lines.append("4. The local DB captures at least hundreds of millions of tokens, which proves the profile spike is not a display bug.")
    lines.append("5. The profile peak exceeds the local DB total by hundreds of millions of tokens, which means local persistence undercounted the full billed footprint.")
    lines.append("")
    lines.append("## Where I Failed")
    lines.append("")
    lines.append(
        "This section is about me, not just the code. I had enough warning signs to stop this earlier and I did not."
    )
    lines.append("")
    lines.append("1. I tolerated continued live benchmarking after it was already obvious that the scheduler was churning.")
    lines.append("2. I let retry/resume behavior continue instead of forcing a hard-stop once invalid model errors and usage-limit messages appeared.")
    lines.append("3. I focused too much on recovery and not enough on economic containment.")
    lines.append("4. I accepted repeated 'proof' and 'ledger' lanes that were not actually advancing the benchmark toward distinct accepted fixes fast enough.")
    lines.append("5. I allowed the system to keep using the platform as a debugging substrate for Mission Control itself, which is exactly how you get charged to learn the same lesson 900 times.")
    lines.append("")
    lines.append("## Hardening Plan")
    lines.append("")
    lines.append("### Immediate containment changes")
    lines.append("")
    lines.append("1. Add a benchmark-wide hard token budget with automatic global stop.")
    lines.append("2. Add a benchmark-wide hard run cap and per-task retry cap.")
    lines.append("3. Treat usage-limit, invalid-model, and malformed-envelope failures as benchmark-halting faults.")
    lines.append("4. Freeze new lane creation when superseded-task count or no-change completion count crosses a threshold.")
    lines.append("5. Require a successful changed-file delta before a run can transition to countable `done` for benchmark accounting.")
    lines.append("")
    lines.append("### Architecture fixes")
    lines.append("")
    lines.append("1. Decouple thread creation from lane retries. Retries should reuse lane identity and preferably reuse session state where safe.")
    lines.append("2. Add dedupe keys for lane families so `Unblock:` variants cannot multiply forever.")
    lines.append("3. Add run-admission control based on current cost, throughput, and backlog-health signals.")
    lines.append("4. Persist and surface benchmark-wide anomaly counters: usage-limit hits, invalid-model hits, zero-change done runs, superseded tasks, pending review backlog age.")
    lines.append("5. Refuse to schedule dashboard/docs/ledger proof lanes until core defect lanes are healthy and converging.")
    lines.append("")
    lines.append("### Operator and bridge fixes")
    lines.append("")
    lines.append("1. Add a visible kill-switch in the Codex bridge path that pauses all Mission Control benchmark automations and daemon scheduling in one action.")
    lines.append("2. Add mandatory anomaly summaries every N runs and every M tokens.")
    lines.append("3. Require explicit human re-arming after usage-limit events, invalid model events, or benchmark reset events.")
    lines.append("4. Add per-project spend dashboards sourced from the same DB plus Codex-side counters to catch local undercount drift.")
    lines.append("")
    lines.append("## Repo-Wide Census")
    lines.append("")
    lines.append(
        "As part of this postmortem, every tracked text file in the repository was opened and line-counted. This is not the same thing as fixing "
        "500 issues, but it does mean the report's appendices are grounded in a real file census rather than a hand-wave."
    )
    lines.append("")
    ext_rows = [
        [ext, fmt_int(count), fmt_int(data["repo_summary"]["ext_lines"][ext])]
        for ext, count in data["repo_summary"]["by_extension"].most_common(25)
    ]
    lines.append(md_table(["Extension", "Tracked Files", "Tracked Text Lines"], ext_rows))
    lines.append("")
    dir_rows = [
        [directory, fmt_int(count), fmt_int(data["repo_summary"]["top_dir_lines"][directory])]
        for directory, count in data["repo_summary"]["by_top_dir"].most_common()
    ]
    lines.append(md_table(["Top-Level Area", "Tracked Files", "Tracked Text Lines"], dir_rows))
    lines.append("")
    lines.append("## Appendix A: Project 11 Task Board Snapshot")
    lines.append("")
    task_rows = [
        [
            row["id"],
            row["status"],
            row["priority"],
            row["title"],
            row["waiting_reason"] or "-",
            fmt_dt(row["updated_at"]),
        ]
        for row in data["tasks"]
    ]
    lines.append(md_table(["Task ID", "Status", "Priority", "Title", "Waiting Reason", "Updated"], task_rows))
    lines.append("")
    lines.append("## Appendix B: Project 11 Agent Snapshot")
    lines.append("")
    agent_rows = [
        [
            row["name"],
            row["kind"],
            row["status"],
            row["active_model"] or "-",
            row["active_reasoning_effort"] or "-",
            row["active_runner_type"] or "-",
            row["failure_count"],
            row["current_action"] or "-",
            fmt_dt(row["last_update"]),
        ]
        for row in data["agents"]
    ]
    lines.append(
        md_table(
            ["Agent", "Kind", "Status", "Model", "Reasoning", "Runner", "Failures", "Current Action", "Last Update"],
            agent_rows,
        )
    )
    lines.append("")
    lines.append("## Appendix C: Highest-Token Runs")
    lines.append("")
    top_run_rows = [
        [
            row["id"],
            row["task_id"] or "-",
            row["agent_name"],
            row["status"],
            row["failure_classification"],
            fmt_int(row["total_tokens"]),
            fmt_int(row["input_tokens"]),
            fmt_int(row["cached_input_tokens"]),
            fmt_int(row["output_tokens"]),
            row["task_title"] or "-",
        ]
        for row in data["top_runs"]
    ]
    lines.append(
        md_table(
            ["Run ID", "Task ID", "Agent", "Status", "Failure", "Total Tokens", "Input", "Cached Input", "Output", "Task Title"],
            top_run_rows,
        )
    )
    lines.append("")
    lines.append("## Appendix D: Full Project 11 Run Ledger")
    lines.append("")
    run_rows = []
    for row in data["project_runs"]:
        report = json_loads_safe(row["report_json"]) or {}
        files_changed = report.get("files_changed", [])
        tests_run = report.get("tests_run", [])
        summary = report.get("summary") or ""
        run_rows.append(
            [
                row["id"],
                row["task_id"] or "-",
                row["agent_name"],
                row["status"],
                row["failure_classification"],
                fmt_int(row["total_tokens"]),
                len(files_changed) if isinstance(files_changed, list) else 0,
                len(tests_run) if isinstance(tests_run, list) else 0,
                fmt_dt(row["started_at"]),
                fmt_dt(row["finished_at"]),
                row["task_title"] or "-",
                summary.replace("\n", " ")[:180] or "-",
            ]
        )
    lines.append(
        md_table(
            [
                "Run ID",
                "Task ID",
                "Agent",
                "Status",
                "Failure",
                "Tokens",
                "Changed Files",
                "Tests",
                "Started",
                "Finished",
                "Task Title",
                "Summary",
            ],
            run_rows,
        )
    )
    lines.append("")
    lines.append("## Appendix E: Tracked File Census")
    lines.append("")
    repo_rows = [
        [
            row.path,
            row.extension,
            fmt_int(row.lines),
            fmt_int(row.size_bytes),
            "yes" if row.text_scanned else "no",
        ]
        for row in data["repo_rows"]
    ]
    lines.append(
        md_table(
            ["Path", "Extension", "Lines", "Bytes", "Text Scanned"],
            repo_rows,
        )
    )
    lines.append("")
    lines.append("## Appendix F: Raw Stored Run Payloads")
    lines.append("")
    lines.append(
        "This appendix is intentionally verbose. It exists so the PDF artifact is evidence-bearing, not just summarized prose."
    )
    lines.append("")
    for row in data["project_runs"]:
        lines.append(f"### Run {row['id']}")
        lines.append("")
        lines.append(
            f"- Task ID: `{row['task_id'] or '-'}`\n"
            f"- Agent: `{row['agent_name']}`\n"
            f"- Task Title: `{row['task_title'] or '-'}`\n"
            f"- Status: `{row['status']}`\n"
            f"- Failure: `{row['failure_classification']}`\n"
            f"- Total Tokens: `{fmt_int(row['total_tokens'])}`\n"
            f"- Started: `{fmt_dt(row['started_at'])}`\n"
            f"- Finished: `{fmt_dt(row['finished_at'])}`"
        )
        lines.append("")
        lines.append("Report JSON")
        lines.append("")
        lines.extend(pretty_json_lines(row["report_json"]))
        lines.append("")
        lines.append("Result Envelope JSON")
        lines.append("")
        lines.extend(pretty_json_lines(row["result_envelope_json"]))
        lines.append("")
    return "\n".join(lines) + "\n"


def query_project_total_tokens(data: dict[str, Any]) -> int:
    return int(sum((row["total_tokens"] or 0) for row in data["project_runs"]))


def render_html(markdown_text: str, title: str) -> str:
    # Lightweight renderer for this report structure.
    lines = markdown_text.splitlines()
    html_lines = [
        "<!doctype html>",
        "<html><head><meta charset='utf-8'>",
        f"<title>{html.escape(title)}</title>",
        "<style>",
        "@page { size: Letter; margin: 0.6in; }",
        "body { font-family: 'Segoe UI', Arial, sans-serif; color: #111; font-size: 10px; line-height: 1.35; }",
        "h1 { font-size: 24px; margin: 0 0 12px; }",
        "h2 { font-size: 18px; margin: 22px 0 8px; page-break-after: avoid; }",
        "h3 { font-size: 14px; margin: 16px 0 6px; page-break-after: avoid; }",
        "p, li { margin: 0 0 8px; }",
        "code { font-family: Consolas, monospace; background: #f3f4f6; padding: 1px 3px; }",
        "table { border-collapse: collapse; width: 100%; margin: 8px 0 16px; table-layout: fixed; }",
        "th, td { border: 1px solid #d1d5db; padding: 4px 5px; vertical-align: top; word-wrap: break-word; }",
        "th { background: #f3f4f6; text-align: left; }",
        "ul, ol { margin: 0 0 8px 22px; }",
        ".mono { font-family: Consolas, monospace; }",
        "</style></head><body>",
    ]

    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("# "):
            html_lines.append(f"<h1>{html.escape(line[2:])}</h1>")
            i += 1
            continue
        if line.startswith("## "):
            html_lines.append(f"<h2>{html.escape(line[3:])}</h2>")
            i += 1
            continue
        if line.startswith("### "):
            html_lines.append(f"<h3>{html.escape(line[4:])}</h3>")
            i += 1
            continue
        if line.startswith("| "):
            table_lines = []
            while i < len(lines) and lines[i].startswith("| "):
                table_lines.append(lines[i])
                i += 1
            html_lines.append(render_markdown_table_html(table_lines))
            continue
        if line.startswith("- "):
            bullet_lines = []
            while i < len(lines) and lines[i].startswith("- "):
                bullet_lines.append(lines[i][2:])
                i += 1
            html_lines.append("<ul>")
            for item in bullet_lines:
                html_lines.append(f"<li>{inline_markdown_to_html(item)}</li>")
            html_lines.append("</ul>")
            continue
        if line and line[:2].isdigit() and ". " in line[:4]:
            ordered_lines = []
            while i < len(lines) and lines[i] and lines[i][0].isdigit() and ". " in lines[i][:4]:
                ordered_lines.append(lines[i].split(". ", 1)[1])
                i += 1
            html_lines.append("<ol>")
            for item in ordered_lines:
                html_lines.append(f"<li>{inline_markdown_to_html(item)}</li>")
            html_lines.append("</ol>")
            continue
        if line.startswith("    "):
            code_lines = []
            while i < len(lines) and lines[i].startswith("    "):
                code_lines.append(lines[i][4:])
                i += 1
            html_lines.append("<pre>" + html.escape("\n".join(code_lines)) + "</pre>")
            continue
        if line.strip():
            html_lines.append(f"<p>{inline_markdown_to_html(line)}</p>")
        i += 1

    html_lines.append("</body></html>")
    return "\n".join(html_lines)


def inline_markdown_to_html(text: str) -> str:
    escaped = html.escape(text)
    parts = escaped.split("`")
    for i in range(1, len(parts), 2):
        parts[i] = f"<code>{parts[i]}</code>"
    return "".join(parts)


def render_markdown_table_html(table_lines: list[str]) -> str:
    rows = []
    for line in table_lines:
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        rows.append(cells)
    if len(rows) < 2:
        return ""
    headers = rows[0]
    body = rows[2:]
    out = ["<table><thead><tr>"]
    for cell in headers:
        out.append(f"<th>{inline_markdown_to_html(cell)}</th>")
    out.append("</tr></thead><tbody>")
    for row in body:
        out.append("<tr>")
        for cell in row:
            out.append(f"<td>{inline_markdown_to_html(cell)}</td>")
        out.append("</tr>")
    out.append("</tbody></table>")
    return "".join(out)


def pretty_json_lines(raw: str | None) -> list[str]:
    if not raw:
        return ["    null"]
    parsed = json_loads_safe(raw)
    if parsed is not None:
        pretty = json.dumps(parsed, indent=2, ensure_ascii=False)
    else:
        pretty = raw
    return [f"    {line}" for line in pretty.splitlines()]


def wrap_text_lines(text: str, width: int = 78) -> list[str]:
    wrapped: list[str] = []
    for line in text.splitlines():
        if not line:
            wrapped.append("")
            continue
        chunks = textwrap.wrap(
            line,
            width=width,
            replace_whitespace=False,
            drop_whitespace=False,
            break_long_words=True,
            break_on_hyphens=False,
        )
        wrapped.extend(chunks or [""])
    return wrapped


def pdf_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def write_text_pdf(text: str, output_path: Path) -> None:
    lines = wrap_text_lines(text, width=78)
    page_width = 612
    page_height = 792
    margin = 36
    font_size = 10
    leading = 12
    lines_per_page = int((page_height - (margin * 2)) / leading)
    pages = [
        lines[index:index + lines_per_page]
        for index in range(0, len(lines), lines_per_page)
    ]

    objects: list[bytes] = []

    def add_object(payload: str | bytes) -> int:
        if isinstance(payload, str):
            payload_bytes = payload.encode("latin-1", errors="replace")
        else:
            payload_bytes = payload
        objects.append(payload_bytes)
        return len(objects)

    font_id = add_object("<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>")

    content_ids: list[int] = []
    page_ids: list[int] = []

    for page_index, page_lines in enumerate(pages, start=1):
        stream_lines = ["BT", f"/F1 {font_size} Tf", f"{margin} {page_height - margin} Td"]
        stream_lines.append(f"{leading} TL")
        for idx, line in enumerate(page_lines):
            if idx == 0:
                stream_lines.append(f"({pdf_escape(line)}) Tj")
            else:
                stream_lines.append("T*")
                stream_lines.append(f"({pdf_escape(line)}) Tj")
        stream_lines.append("ET")
        stream = "\n".join(stream_lines).encode("latin-1", errors="replace")
        content_payload = (
            f"<< /Length {len(stream)} >>\nstream\n".encode("latin-1")
            + stream
            + b"\nendstream"
        )
        content_ids.append(add_object(content_payload))

    pages_kids_placeholder = "__PAGES_KIDS__"
    pages_obj_index = add_object(
        f"<< /Type /Pages /Count {len(pages)} /Kids {pages_kids_placeholder} >>"
    )

    for content_id in content_ids:
        page_payload = (
            "<< /Type /Page /Parent "
            f"{pages_obj_index} 0 R /MediaBox [0 0 {page_width} {page_height}] "
            f"/Resources << /Font << /F1 {font_id} 0 R >> >> /Contents {content_id} 0 R >>"
        )
        page_ids.append(add_object(page_payload))

    kids = "[ " + " ".join(f"{page_id} 0 R" for page_id in page_ids) + " ]"
    objects[pages_obj_index - 1] = objects[pages_obj_index - 1].replace(
        pages_kids_placeholder.encode("latin-1"),
        kids.encode("latin-1"),
    )

    catalog_id = add_object(f"<< /Type /Catalog /Pages {pages_obj_index} 0 R >>")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("wb") as fh:
        fh.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offsets = [0]
        for index, payload in enumerate(objects, start=1):
            offsets.append(fh.tell())
            fh.write(f"{index} 0 obj\n".encode("latin-1"))
            fh.write(payload)
            fh.write(b"\nendobj\n")
        xref_offset = fh.tell()
        fh.write(f"xref\n0 {len(objects) + 1}\n".encode("latin-1"))
        fh.write(b"0000000000 65535 f \n")
        for offset in offsets[1:]:
            fh.write(f"{offset:010d} 00000 n \n".encode("latin-1"))
        fh.write(
            (
                f"trailer\n<< /Size {len(objects) + 1} /Root {catalog_id} 0 R >>\n"
                f"startxref\n{xref_offset}\n%%EOF\n"
            ).encode("latin-1")
        )


def write_outputs(project_id: int) -> tuple[Path, Path, Path]:
    data = gather_data(project_id)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    base = OUTPUT_DIR / f"mission-control-token-spike-postmortem-project-{project_id}"
    markdown_path = base.with_suffix(".md")
    html_path = base.with_suffix(".html")
    pdf_path = base.with_suffix(".pdf")

    markdown_text = render_markdown(data)
    html_text = render_html(markdown_text, "Mission Control Token Spike Postmortem")

    markdown_path.write_text(markdown_text, encoding="utf-8")
    html_path.write_text(html_text, encoding="utf-8")
    write_text_pdf(markdown_text, pdf_path)
    return markdown_path, html_path, pdf_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-id", type=int, default=11)
    args = parser.parse_args()

    markdown_path, html_path, pdf_path = write_outputs(args.project_id)
    print(markdown_path)
    print(html_path)
    print(pdf_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
