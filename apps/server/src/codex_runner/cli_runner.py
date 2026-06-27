from __future__ import annotations

import asyncio
import codecs
import json
import os
import re
import shutil
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from codex_runner.base import BaseCodexRunner, RunnerContext, RunnerHandle
from codex_runner.events import parse_json_line
from codex_cli_path import codex_command_path
from config import RUNTIME_LOGS_ROOT, RUNTIME_ROOT
from prompts import worker_task_prompt
from provider_support import default_label
from usage_tracking import build_prompt_usage_estimate
from workspace_git import workspace_git_env


@dataclass
class CliRunState:
    process: asyncio.subprocess.Process | None = None
    status: str = "starting"
    events: list[dict[str, Any]] = field(default_factory=list)
    cursor: int = 0
    logs_path: str | None = None
    stdout_path: str | None = None
    stderr_path: str | None = None
    event_log_path: str | None = None
    final_text: str | None = None
    session_ref: str | None = None
    reader_task: asyncio.Task | None = None
    exit_code: int | None = None
    cli_version: str | None = None
    login_status: str | None = None
    effective_settings: dict[str, Any] = field(default_factory=dict)
    agent_name: str | None = None
    task_id: str | None = None


class CliCodexRunner(BaseCodexRunner):
    runner_type = "codex_cli"
    auth_files = ("auth.json", ".credentials.json", "installation_id")
    windows_env_keys = (
        "SystemRoot",
        "ComSpec",
        "PATHEXT",
        "WINDIR",
        "OS",
        "ProgramFiles",
        "ProgramFiles(x86)",
        "ProgramW6432",
        "PROCESSOR_ARCHITECTURE",
        "PROCESSOR_IDENTIFIER",
        "NUMBER_OF_PROCESSORS",
        "TEMP",
        "TMP",
        "LOCALAPPDATA",
        "APPDATA",
        "ProgramData",
        "USERNAME",
        "USERDOMAIN",
        "HOMEDRIVE",
        "HOMEPATH",
    )
    posix_env_keys = (
        "PATH",
        "HOME",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "SHELL",
        "TERM",
        "TMPDIR",
        "XDG_RUNTIME_DIR",
        "XDG_CONFIG_HOME",
        "XDG_CACHE_HOME",
        "XDG_DATA_HOME",
    )
    startup_disable_features = ("apps", "plugins", "tool_suggest")
    stripped_parent_session_env = (
        "CODEX_INTERNAL_ORIGINATOR_OVERRIDE",
        "CODEX_THREAD_ID",
        "CODEX_SHELL",
    )
    non_actionable_stderr_markers = (
        "Reading additional input from stdin...",
        "codex_models_manager::manager: failed to refresh available models",
        "codex_analytics::client: failed to send events request",
    )
    windows_required_commands = (
        "powershell.exe",
        "where.exe",
        "git.exe",
        "python.exe",
        "py.exe",
        "node.exe",
        "npm.cmd",
        "rg.exe",
    )

    def __init__(self) -> None:
        self.runs: dict[str, CliRunState] = {}
        self.last_cli_version: str | None = None
        self.last_login_status: str | None = None
        self.last_cli_path: str | None = None

    async def handshake(self, settings=None) -> bool:
        cli_path = codex_command_path()
        self.last_cli_path = cli_path
        if cli_path is None:
            self.last_cli_version = None
            return False
        env = self.build_subprocess_env()
        try:
            process = await asyncio.create_subprocess_exec(
                cli_path,
                "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                **self.quiet_subprocess_kwargs(),
            )
        except OSError:
            return False
        stdout, stderr = await process.communicate()
        if process.returncode == 0:
            self.last_cli_version = (stdout or stderr).decode("utf-8", errors="ignore").strip() or None
        await self._refresh_login_status()
        return process.returncode == 0

    async def _refresh_login_status(self) -> None:
        cli_path = self.last_cli_path or codex_command_path()
        self.last_cli_path = cli_path
        if cli_path is None:
            self.last_login_status = "Unavailable"
            return
        try:
            process = await asyncio.create_subprocess_exec(
                cli_path,
                "login",
                "status",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=self.build_subprocess_env(),
                **self.quiet_subprocess_kwargs(),
            )
        except OSError:
            self.last_login_status = "Unavailable"
            return
        stdout, stderr = await process.communicate()
        self.last_login_status = (stdout or stderr).decode("utf-8", errors="ignore").strip() or "Unavailable"

    async def start_task(self, context: RunnerContext) -> RunnerHandle:
        prompt = await asyncio.to_thread(
            worker_task_prompt,
            context.project,
            context.agent,
            context.task,
            context.docs_path,
            context.plan_markdown,
            provider=context.settings.provider,
            model=context.settings.model,
            reasoning_effort=context.settings.reasoning_effort,
        )
        return await self._start_process(context, prompt, resume=False)

    async def resume_or_continue(self, context: RunnerContext, message: str) -> RunnerHandle:
        return await self._start_process(context, message, resume=True)

    async def stop_run(self, run_id: str) -> None:
        state = self.runs.get(run_id)
        if not state or not state.process:
            return
        state.process.terminate()
        state.status = "stopped"

    async def read_events(self, run_id: str) -> list[dict[str, Any]]:
        state = self.runs.get(run_id)
        if not state:
            return []
        events = state.events[state.cursor :]
        state.cursor = len(state.events)
        return events

    async def get_status(self, run_id: str) -> str:
        state = self.runs.get(run_id)
        return state.status if state else "error"

    @staticmethod
    def subprocess_cwd(context: RunnerContext) -> str:
        return CliCodexRunner.effective_workspace_path(context)

    def build_exec_args(self, context: RunnerContext, *, resume: bool) -> list[str]:
        workdir = self.subprocess_cwd(context)
        cli_path = self.last_cli_path or codex_command_path()
        if cli_path is None:
            raise RuntimeError("Codex CLI resolved path is unavailable.")
        self.last_cli_path = cli_path
        base_args = [cli_path]
        for feature in self.startup_disable_features:
            base_args.extend(["--disable", feature])
        if context.settings.approval_policy:
            base_args.extend(["-a", context.settings.approval_policy])
        sandbox_mode = self.effective_sandbox_mode(context)
        if sandbox_mode:
            base_args.extend(["--sandbox", sandbox_mode])
        if resume and context.agent.session_ref:
            base_args.extend(["exec", "resume", "--json", "--skip-git-repo-check", "--ignore-user-config", "--ignore-rules"])
            if context.settings.model:
                base_args.extend(["-m", context.settings.model])
            if context.settings.reasoning_effort:
                base_args.extend(["-c", f'model_reasoning_effort="{context.settings.reasoning_effort}"'])
            base_args.extend([context.agent.session_ref, "-"])
            return base_args

        base_args.extend(["exec", "--json", "--skip-git-repo-check", "--ignore-user-config", "--ignore-rules"])
        if context.settings.model:
            base_args.extend(["-m", context.settings.model])
        if context.settings.reasoning_effort:
            base_args.extend(["-c", f'model_reasoning_effort="{context.settings.reasoning_effort}"'])
        base_args.extend(["-C", workdir, "-"])
        return base_args

    def _source_codex_home(self) -> Path:
        candidate = (
            os.environ.get("MISSION_CONTROL_SOURCE_CODEX_HOME")
            or os.environ.get("CODEX_HOME")
            or str(Path.home() / ".codex")
        )
        return Path(candidate).expanduser().resolve()

    def _source_home_value(self) -> str | None:
        return os.environ.get("MISSION_CONTROL_SOURCE_HOME") or os.environ.get("HOME")

    def _source_userprofile_value(self) -> str | None:
        return (
            os.environ.get("MISSION_CONTROL_SOURCE_USERPROFILE")
            or os.environ.get("USERPROFILE")
            or self._source_home_value()
        )

    def _source_localappdata_value(self) -> str | None:
        explicit = os.environ.get("MISSION_CONTROL_SOURCE_LOCALAPPDATA")
        if explicit:
            return explicit
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            return local_app_data
        source_userprofile = self._source_userprofile_value()
        if source_userprofile:
            return str(Path(source_userprofile) / "AppData" / "Local")
        return None

    @staticmethod
    def _programfiles_values() -> list[str]:
        values = [
            os.environ.get("ProgramFiles"),
            os.environ.get("ProgramFiles(x86)"),
            os.environ.get("ProgramW6432"),
        ]
        deduped: list[str] = []
        seen: set[str] = set()
        for value in values:
            text = str(value or "").strip()
            if not text:
                continue
            normalized = os.path.normcase(text)
            if normalized in seen:
                continue
            seen.add(normalized)
            deduped.append(text)
        return deduped

    def _profile_root(self) -> Path:
        return (RUNTIME_ROOT / "codex-profile").resolve()

    def _runtime_codex_home(self) -> Path:
        return self._profile_root() / ".codex"

    def _context_profile_slug(self, context: RunnerContext) -> str:
        project_part = str(getattr(context.project, "id", "") or "project")
        agent_part = str(getattr(context.agent, "id", "") or getattr(context.agent, "name", "") or "agent")
        kind_part = str(getattr(context.agent, "kind", "") or "worker")
        raw = f"{kind_part}-{project_part}-{agent_part}"
        slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", raw).strip("-._")
        return slug or "worker"

    def _context_profile_root(self, context: RunnerContext) -> Path:
        return self._profile_root() / self._context_profile_slug(context)

    def _mirror_auth_assets(self, target_codex_home: Path) -> None:
        source_codex_home = self._source_codex_home()
        target_codex_home.mkdir(parents=True, exist_ok=True)
        for name in self.auth_files:
            source = source_codex_home / name
            if not source.exists() or not source.is_file():
                continue
            shutil.copy2(source, target_codex_home / name)

    @classmethod
    def _nested_codex_desktop_runtime(cls) -> bool:
        return any(
            os.environ.get(key)
            for key in cls.stripped_parent_session_env
        )

    @classmethod
    def effective_sandbox_mode(cls, context: RunnerContext) -> str:
        requested = context.settings.sandbox_mode or "workspace-write"
        if requested == "workspace-write":
            # Codex CLI does not reliably preserve workspace-write in the
            # desktop-managed runtimes Mission Control targets today. Promote to
            # explicit danger-full-access so internal manager and worker turns
            # can actually mutate the approved workspace instead of silently
            # degrading into read-only execution.
            return "danger-full-access"
        return requested

    def _apply_codex_profile_env(self, env: dict[str, str], *, profile_root: Path) -> dict[str, str]:
        codex_home = profile_root / ".codex"
        profile_root.mkdir(parents=True, exist_ok=True)
        self._mirror_auth_assets(codex_home)
        shim_dirs: list[str] = []
        if os.name == "nt":
            shim_dirs = self._ensure_windows_tool_shims(profile_root)

        env["HOME"] = str(profile_root)
        source_home = self._source_home_value()
        if source_home:
            env.setdefault("MISSION_CONTROL_SOURCE_HOME", source_home)
        if os.name == "nt":
            env["USERPROFILE"] = str(profile_root)
            source_userprofile = self._source_userprofile_value()
            if source_userprofile:
                env.setdefault("MISSION_CONTROL_SOURCE_USERPROFILE", source_userprofile)
        env["CODEX_HOME"] = str(codex_home)
        env["MISSION_CONTROL_CODEX_HOME"] = str(codex_home)
        env.setdefault("MISSION_CONTROL_SOURCE_CODEX_HOME", str(self._source_codex_home()))
        if os.name == "nt":
            existing_entries = [
                entry
                for entry in (env.get("Path") or env.get("PATH") or "").split(os.pathsep)
                if entry
            ]
            expanded_path = os.pathsep.join(self._dedupe_windows_path_entries([*shim_dirs, *existing_entries]))
            env["Path"] = expanded_path
            env["PATH"] = expanded_path
        return env

    @staticmethod
    def _expand_path_entry(entry: str, overrides: dict[str, str]) -> str:
        env_values = {key.upper(): value for key, value in os.environ.items() if value}
        env_values.update({key.upper(): value for key, value in overrides.items() if value})

        def replace_windows_var(match: re.Match[str]) -> str:
            key = match.group(1).upper()
            return env_values.get(key, match.group(0))

        def replace_braced_var(match: re.Match[str]) -> str:
            key = match.group(1).upper()
            return env_values.get(key, match.group(0))

        def replace_plain_var(match: re.Match[str]) -> str:
            key = match.group(1).upper()
            return env_values.get(key, match.group(0))

        expanded = re.sub(r"%([^%]+)%", replace_windows_var, entry)
        expanded = re.sub(r"\$\{([^}]+)\}", replace_braced_var, expanded)
        expanded = re.sub(r"\$([A-Za-z_][A-Za-z0-9_]*)", replace_plain_var, expanded)
        return expanded

    @staticmethod
    def _dedupe_windows_path_entries(entries: list[str]) -> list[str]:
        unique: list[str] = []
        seen: set[str] = set()
        for raw_entry in entries:
            entry = str(raw_entry or "").strip().strip('"')
            if not entry:
                continue
            normalized = os.path.normcase(os.path.normpath(entry))
            if normalized in seen:
                continue
            seen.add(normalized)
            unique.append(entry)
        return unique

    def _augment_windows_path_entries(self, base_entries: list[str]) -> list[str]:
        entries = list(base_entries)
        system_root = os.environ.get("SystemRoot") or os.environ.get("WINDIR") or r"C:\Windows"
        system_root_path = Path(system_root)
        entries.extend(
            [
                str((system_root_path / "System32").resolve()),
                str(system_root_path.resolve()),
                str((system_root_path / "System32" / "WindowsPowerShell" / "v1.0").resolve()),
            ]
        )
        codex_path = self.last_cli_path or codex_command_path()
        if codex_path:
            entries.append(str(Path(codex_path).resolve().parent))
        for command in self.windows_required_commands:
            resolved = self._resolve_windows_command_path(command)
            if not resolved:
                continue
            entries.append(str(Path(resolved).resolve().parent))
        return self._dedupe_windows_path_entries(entries)

    def _windows_command_candidate_paths(self, command: str) -> list[Path]:
        normalized = str(command or "").strip().lower()
        if not normalized:
            return []
        local_app_data = self._source_localappdata_value()
        local_app_data_path = Path(local_app_data).expanduser() if local_app_data else None
        system_root = os.environ.get("SystemRoot") or os.environ.get("WINDIR") or r"C:\Windows"
        system_root_path = Path(system_root).expanduser()
        program_files_paths = [Path(value).expanduser() for value in self._programfiles_values()]
        candidates: list[Path] = []
        if normalized == "powershell.exe":
            candidates.append(system_root_path / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe")
        elif normalized == "where.exe":
            candidates.append(system_root_path / "System32" / "where.exe")
        elif normalized == "git.exe":
            for root in program_files_paths:
                candidates.extend(
                    [
                        root / "Git" / "cmd" / "git.exe",
                        root / "Git" / "bin" / "git.exe",
                    ]
                )
        elif normalized == "python.exe":
            if local_app_data_path is not None:
                candidates.extend(sorted((local_app_data_path / "Programs" / "Python").glob("Python*\\python.exe"), reverse=True))
                candidates.append(local_app_data_path / "Microsoft" / "WindowsApps" / "python.exe")
        elif normalized == "py.exe":
            if local_app_data_path is not None:
                candidates.extend(
                    [
                        local_app_data_path / "Programs" / "Python" / "Launcher" / "py.exe",
                        local_app_data_path / "Microsoft" / "WindowsApps" / "py.exe",
                    ]
                )
        elif normalized == "node.exe":
            for root in program_files_paths:
                candidates.append(root / "nodejs" / "node.exe")
        elif normalized == "npm.cmd":
            for root in program_files_paths:
                candidates.extend(
                    [
                        root / "nodejs" / "npm.cmd",
                        root / "nodejs" / "npm.ps1",
                    ]
                )
        elif normalized == "rg.exe":
            codex_path = self.last_cli_path or codex_command_path()
            if codex_path:
                codex_bin = Path(codex_path).resolve().parent
                candidates.append(codex_bin / "rg.exe")
                candidates.extend(sorted(codex_bin.glob("*\\rg.exe"), reverse=True))
            if local_app_data_path is not None:
                codex_bin_root = local_app_data_path / "OpenAI" / "Codex" / "bin"
                candidates.append(codex_bin_root / "rg.exe")
                candidates.extend(sorted(codex_bin_root.glob("*\\rg.exe"), reverse=True))
        deduped: list[Path] = []
        seen: set[str] = set()
        for candidate in candidates:
            normalized_candidate = os.path.normcase(str(candidate))
            if normalized_candidate in seen:
                continue
            seen.add(normalized_candidate)
            deduped.append(candidate)
        return deduped

    def _resolve_windows_command_path(self, command: str) -> str | None:
        resolved = shutil.which(command)
        if resolved:
            return resolved
        for candidate in self._windows_command_candidate_paths(command):
            if candidate.exists():
                try:
                    return str(candidate.resolve())
                except OSError:
                    return str(candidate)
        return None

    @staticmethod
    def _windows_tool_shim_targets() -> tuple[tuple[str, tuple[str, ...]], ...]:
        return (
            ("git", ("git.exe", "git")),
            ("python", ("python.exe", "python")),
            ("py", ("py.exe", "py")),
            ("node", ("node.exe", "node")),
            ("npm", ("npm.cmd", "npm.ps1", "npm")),
            ("rg", ("rg.exe", "rg")),
        )

    @staticmethod
    def _write_windows_wrapper(wrapper_path: Path, target_path: str) -> None:
        target = Path(target_path)
        command = f'call "{target}" %*\n' if target.suffix.lower() in {".cmd", ".bat"} else f'"{target}" %*\n'
        wrapper_path.write_text(f"@echo off\n{command}", encoding="utf-8")

    def _ensure_windows_tool_shims(self, profile_root: Path) -> list[str]:
        shim_dirs = [
            profile_root / "tool-bin",
            profile_root / "AppData" / "Local" / "Microsoft" / "WindowsApps",
        ]
        for directory in shim_dirs:
            directory.mkdir(parents=True, exist_ok=True)
        for alias, candidates in self._windows_tool_shim_targets():
            resolved_path = None
            for candidate in candidates:
                resolved_path = self._resolve_windows_command_path(candidate)
                if resolved_path:
                    break
            if not resolved_path:
                continue
            for directory in shim_dirs:
                self._write_windows_wrapper(directory / f"{alias}.cmd", resolved_path)
        return [str(directory) for directory in shim_dirs]

    def build_subprocess_env(self) -> dict[str, str]:
        env: dict[str, str] = {}
        inherited_keys = self.windows_env_keys if os.name == "nt" else self.posix_env_keys
        for key in inherited_keys:
            value = os.environ.get(key)
            if value:
                env[key] = value
        if os.name == "nt":
            path_value = os.environ.get("Path") or os.environ.get("PATH")
            if path_value:
                # Expand PATH aliases against the preserved host profile values.
                # The daemon intentionally rewrites HOME/USERPROFILE to an
                # isolated runtime root, so blindly using os.path.expandvars here
                # corrupts entries such as %USERPROFILE%\AppData\Local\Microsoft\WindowsApps.
                path_overrides = {
                    "HOME": self._source_home_value() or "",
                    "USERPROFILE": self._source_userprofile_value() or "",
                }
                expanded_entries = [
                    self._expand_path_entry(entry, path_overrides)
                    for entry in path_value.split(os.pathsep)
                    if str(entry or "").strip()
                ]
                expanded_path = os.pathsep.join(self._augment_windows_path_entries(expanded_entries))
                env["Path"] = expanded_path
                env["PATH"] = expanded_path
        else:
            path_value = os.environ.get("PATH")
            if path_value:
                env["PATH"] = path_value
        for key in self.stripped_parent_session_env:
            env.pop(key, None)
        if os.name == "nt" and "Path" not in env and "PATH" in env:
            env["Path"] = env["PATH"]
        if os.name == "nt" and "PATH" not in env and "Path" in env:
            env["PATH"] = env["Path"]

        return self._apply_codex_profile_env(env, profile_root=self._profile_root())

    def build_context_subprocess_env(self, context: RunnerContext) -> dict[str, str]:
        return self._apply_codex_profile_env(
            self.build_subprocess_env(),
            profile_root=self._context_profile_root(context),
        )

    @classmethod
    def _filter_stderr_lines(cls, lines: list[str], *, status: str) -> list[str]:
        if status != "done":
            return lines
        filtered: list[str] = []
        for line in lines:
            if any(marker in line for marker in cls.non_actionable_stderr_markers):
                continue
            filtered.append(line)
        return filtered

    async def _start_process(self, context: RunnerContext, prompt: str, resume: bool) -> RunnerHandle:
        if not await self.handshake():
            raise RuntimeError("Codex CLI is not available on PATH.")
        run_id = f"cli-{uuid.uuid4().hex}"
        initial_usage = build_prompt_usage_estimate(prompt)
        logs_path = RUNTIME_LOGS_ROOT / f"{run_id}.log"
        stdout_path = RUNTIME_LOGS_ROOT / f"{run_id}.stdout.log"
        stderr_path = RUNTIME_LOGS_ROOT / f"{run_id}.stderr.log"
        event_log_path = RUNTIME_LOGS_ROOT / f"{run_id}.events.jsonl"
        self.ensure_log_parent(logs_path)
        state = CliRunState(
            logs_path=str(logs_path),
            stdout_path=str(stdout_path),
            stderr_path=str(stderr_path),
            event_log_path=str(event_log_path),
            cli_version=self.last_cli_version,
            login_status=self.last_login_status,
            effective_settings={
                "provider": context.settings.provider,
                "model": context.settings.model or default_label(context.settings.provider),
                "reasoning_effort": context.settings.reasoning_effort or default_label(context.settings.provider),
                "sandbox_mode": self.effective_sandbox_mode(context),
                "approval_policy": context.settings.approval_policy,
            },
            agent_name=context.agent.name,
            task_id=str(context.task.id) if context.task is not None else "unknown",
        )
        self.runs[run_id] = state

        base_args = self.build_exec_args(context, resume=resume)
        workdir = self.subprocess_cwd(context)
        env = workspace_git_env(workdir, self.build_context_subprocess_env(context))

        state.process = await asyncio.create_subprocess_exec(
            *base_args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=workdir,
            env=env,
            **self.quiet_subprocess_kwargs(),
        )
        assert state.process.stdin is not None
        state.process.stdin.write(prompt.encode("utf-8"))
        await state.process.stdin.drain()
        state.process.stdin.close()
        state.reader_task = asyncio.create_task(self._consume_process(run_id))
        return RunnerHandle(
            id=run_id,
            runner_type=self.runner_type,
            logs_path=str(logs_path),
            stdout_path=str(stdout_path),
            stderr_path=str(stderr_path),
            event_log_path=str(event_log_path),
            initial_usage=initial_usage,
        )

    def _handle_stdout_event(self, state: CliRunState, text: str, event_lines: list[str]) -> None:
        parsed = parse_json_line(text)
        if not parsed:
            return
        event_lines.append(json.dumps(parsed))
        event_type = parsed.get("type", "unknown")
        if event_type == "thread.started":
            state.session_ref = parsed.get("thread_id")
        if event_type == "turn.started":
            state.status = "working"
            parsed["effective_settings"] = state.effective_settings
        if event_type == "turn.completed":
            # Do not mark the run terminal yet. The CLI can still be draining
            # trailing structured agent_message output that Mission Control must
            # ingest before the monitor loop finalizes the run.
            state.status = "working"
        if event_type == "turn.failed" or event_type == "error":
            state.status = "error"
        item = parsed.get("item")
        if isinstance(item, dict) and item.get("type") == "agent_message":
            state.final_text = item.get("text")
        state.events.append(parsed)

    @staticmethod
    def _drain_complete_lines(buffer: str) -> tuple[list[str], str]:
        lines: list[str] = []
        while True:
            newline_index = buffer.find("\n")
            if newline_index < 0:
                break
            lines.append(buffer[:newline_index].rstrip("\r"))
            buffer = buffer[newline_index + 1 :]
        return lines, buffer

    async def _read_stdout_stream(
        self,
        state: CliRunState,
        stdout: asyncio.StreamReader | None,
        stdout_lines: list[str],
        log_lines: list[str],
        event_lines: list[str],
    ) -> None:
        if stdout is None:
            return
        decoder = codecs.getincrementaldecoder("utf-8")(errors="ignore")
        buffer = ""
        while True:
            chunk = await stdout.read(16384)
            if not chunk:
                break
            buffer += decoder.decode(chunk)
            completed_lines, buffer = self._drain_complete_lines(buffer)
            for text in completed_lines:
                stdout_lines.append(text)
                log_lines.append(text)
                self._handle_stdout_event(state, text, event_lines)
        buffer += decoder.decode(b"", final=True)
        if buffer:
            text = buffer.rstrip("\r")
            stdout_lines.append(text)
            log_lines.append(text)
            self._handle_stdout_event(state, text, event_lines)

    async def _read_stderr_stream(
        self,
        stderr: asyncio.StreamReader | None,
        stderr_lines: list[str],
        log_lines: list[str],
    ) -> None:
        if stderr is None:
            return
        decoder = codecs.getincrementaldecoder("utf-8")(errors="ignore")
        buffer = ""
        while True:
            chunk = await stderr.read(16384)
            if not chunk:
                break
            buffer += decoder.decode(chunk)
            completed_lines, buffer = self._drain_complete_lines(buffer)
            for text in completed_lines:
                if not text:
                    continue
                stderr_lines.append(text)
                log_lines.append(text)
        buffer += decoder.decode(b"", final=True)
        if buffer:
            text = buffer.rstrip("\r")
            if text:
                stderr_lines.append(text)
                log_lines.append(text)

    async def _consume_process(self, run_id: str) -> None:
        state = self.runs[run_id]
        assert state.process is not None
        try:
            stdout = state.process.stdout
            stderr = state.process.stderr
            log_lines: list[str] = []
            stdout_lines: list[str] = []
            stderr_lines: list[str] = []
            event_lines: list[str] = []
            await asyncio.gather(
                self._read_stdout_stream(state, stdout, stdout_lines, log_lines, event_lines),
                self._read_stderr_stream(stderr, stderr_lines, log_lines),
            )

            returncode = await state.process.wait()
            state.exit_code = returncode
            if state.status == "starting":
                state.status = "done" if returncode == 0 else "error"
            elif returncode == 0 and state.status == "working" and self._has_structured_result(state):
                # Successful runs can intentionally stay "working" through
                # turn.completed while trailing structured output drains. Once
                # the process exits cleanly and a structured result exists,
                # promote the state to terminal "done" so Mission Control can
                # finalize the report instead of leaving the worker stuck busy.
                state.status = "done"
            if returncode != 0 and state.status != "stopped":
                state.status = "error"
            if state.status != "done" and not self._has_structured_result(state):
                failure_event = self._build_failure_result_event(state, stdout_lines, stderr_lines)
                state.final_text = failure_event["item"]["text"]
                state.events.append(failure_event)
                event_lines.append(json.dumps(failure_event))
            stderr_lines = self._filter_stderr_lines(stderr_lines, status=state.status)
            log_lines = stdout_lines + stderr_lines
            Path(state.logs_path or "").write_text("\n".join(log_lines), encoding="utf-8")
            Path(state.stdout_path or "").write_text("\n".join(stdout_lines), encoding="utf-8")
            Path(state.stderr_path or "").write_text("\n".join(stderr_lines), encoding="utf-8")
            Path(state.event_log_path or "").write_text("\n".join(event_lines), encoding="utf-8")
        finally:
            self.finalize_subprocess_state(state)

    @classmethod
    def _has_structured_result(cls, state: CliRunState) -> bool:
        for event in state.events:
            item = event.get("item")
            if not isinstance(item, dict) or item.get("type") != "agent_message":
                continue
            text = item.get("text")
            if (
                cls.try_parse_result_envelope(text)
                or cls.try_parse_report(text)
                or cls.try_parse_structured_message_payload(text)
            ):
                return True
        return False

    @staticmethod
    def _classify_failure_text(text: str) -> str:
        haystack = text.lower()
        if any(token in haystack for token in ("approval denied", "user denied")):
            return "approval_denied"
        if any(token in haystack for token in ("usage limit", "rate limit", "quota", "try again at", "too many requests")):
            return "transient"
        if any(token in haystack for token in ("auth", "api key", "login", "token expired", "credential", "permission required", "purchase more credits")):
            return "user_action_required"
        if any(token in haystack for token in ("database is locked", "timeout", "temporar", "connection reset", "network", "stream disconnected")):
            return "transient"
        if any(token in haystack for token in ("gpu", "cluster", "pod pending", "infra", "kubernetes", "disk full", "resource unavailable")):
            return "infra_blocker"
        return "runner_bug"

    def _build_failure_result_event(
        self,
        state: CliRunState,
        stdout_lines: list[str],
        stderr_lines: list[str],
    ) -> dict[str, Any]:
        diagnostics: list[str] = []
        for event in state.events:
            if event.get("type") == "error":
                message = event.get("message")
                if isinstance(message, str) and message.strip():
                    diagnostics.append(message.strip())
            if event.get("type") == "turn.failed":
                error = event.get("error")
                if isinstance(error, dict):
                    message = error.get("message")
                    if isinstance(message, str) and message.strip():
                        diagnostics.append(message.strip())
        diagnostics.extend(line.strip() for line in stderr_lines if line.strip())
        if not diagnostics:
            diagnostics.extend(line.strip() for line in stdout_lines if line.strip())
        diagnostics = list(dict.fromkeys(diagnostics))
        summary = diagnostics[0] if diagnostics else "Codex CLI failed before producing a structured report."
        failure_classification = self._classify_failure_text(" ".join(diagnostics or [summary]))
        report_status = "blocked" if failure_classification in {"transient", "user_action_required", "infra_blocker", "approval_denied"} else "error"
        envelope_status = "blocked" if report_status == "blocked" else "failed"
        envelope = {
            "status": envelope_status,
            "runner_type": self.runner_type,
            "lane": "implementation",
            "summary": summary,
            "report": {
                "agent": state.agent_name or "Unknown agent",
                "task_id": state.task_id or "unknown",
                "status": report_status,
                "summary": summary,
                "files_changed": [],
                "tests_run": [],
                "blockers": [summary] if report_status == "blocked" else [],
                "risks": diagnostics[:10],
                "recommended_next_task": "Retry after the provider/runtime blocker is resolved." if report_status == "blocked" else "",
            },
            "files_changed": [],
            "tests_run": [],
            "commands_attempted": [],
            "evidence": [],
            "risks": diagnostics[:10],
            "blockers": [summary] if report_status == "blocked" else [],
            "diagnostics": diagnostics[:10],
            "approvals_requested": [],
            "recovery_plan": ["Retry the run once the provider/runtime issue is resolved."] if report_status == "blocked" else [],
            "edits": [],
            "failure_classification": failure_classification,
            "needs_approval": False,
            "metadata_json": {
                "synthetic_failure_envelope": True,
                "exit_code": state.exit_code,
            },
        }
        return {
            "type": "item.completed",
            "item": {"type": "agent_message", "text": json.dumps(envelope)},
            "effective_settings": state.effective_settings,
        }
