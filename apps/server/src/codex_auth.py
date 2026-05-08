from __future__ import annotations

import asyncio
import shutil
import subprocess
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import RUNTIME_ROOT
from system_status import auth_mode_from_login_output, detect_codex_status


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _creationflags() -> int:
    if hasattr(subprocess, "CREATE_NO_WINDOW"):
        return subprocess.CREATE_NO_WINDOW
    return 0


@dataclass
class AuthJobState:
    id: str
    method: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    exit_code: int | None
    message: str
    log_path: str | None
    output_lines: list[str] = field(default_factory=list)
    auth_mode_after: str | None = None


class CodexAuthService:
    def __init__(self) -> None:
        self.jobs: dict[str, AuthJobState] = {}
        self.active_job_id: str | None = None
        self._lock = asyncio.Lock()
        self._jobs_root = RUNTIME_ROOT / "auth"
        self._jobs_root.mkdir(parents=True, exist_ok=True)

    def current_job(self) -> AuthJobState | None:
        if self.active_job_id is None:
            if not self.jobs:
                return None
            return max(self.jobs.values(), key=lambda item: item.started_at)
        job = self.jobs.get(self.active_job_id)
        if job is not None:
            return job
        if not self.jobs:
            return None
        return max(self.jobs.values(), key=lambda item: item.started_at)

    def job_payload(self, job: AuthJobState | None) -> dict[str, Any] | None:
        if job is None:
            return None
        return {
            "id": job.id,
            "method": job.method,
            "status": job.status,
            "started_at": job.started_at,
            "finished_at": job.finished_at,
            "exit_code": job.exit_code,
            "message": job.message,
            "auth_mode_after": job.auth_mode_after,
            "log_path": job.log_path,
            "output_lines": job.output_lines[-12:],
        }

    def get_job(self, job_id: str) -> AuthJobState | None:
        return self.jobs.get(job_id)

    async def start_chatgpt_login(self, *, device_auth: bool = False) -> AuthJobState:
        args = ["codex", "login"]
        method = "chatgpt"
        message = "Waiting for Codex ChatGPT sign-in to finish."
        if device_auth:
            args.append("--device-auth")
            method = "device_auth"
            message = "Waiting for Codex device-code sign-in to finish."
        return await self._start_job(method=method, args=args, stdin_text=None, initial_message=message)

    async def start_api_key_login(self, api_key: str) -> AuthJobState:
        cleaned = api_key.strip()
        if not cleaned:
            raise ValueError("API key is required.")
        return await self._start_job(
            method="api_key",
            args=["codex", "login", "--with-api-key"],
            stdin_text=cleaned + "\n",
            initial_message="Sending the API key to the local Codex CLI login flow.",
        )

    async def start_logout(self) -> AuthJobState:
        return await self._start_job(
            method="logout",
            args=["codex", "logout"],
            stdin_text=None,
            initial_message="Signing out of the local Codex CLI session.",
        )

    async def _start_job(self, *, method: str, args: list[str], stdin_text: str | None, initial_message: str) -> AuthJobState:
        if shutil.which("codex") is None:
            raise RuntimeError("Codex CLI was not found on PATH.")
        async with self._lock:
            current = self.current_job()
            if current is not None:
                raise RuntimeError("Another authentication flow is already running.")
            job_id = f"auth-{uuid.uuid4().hex}"
            log_path = self._jobs_root / f"{job_id}.log"
            job = AuthJobState(
                id=job_id,
                method=method,
                status="queued",
                started_at=_utc_now(),
                finished_at=None,
                exit_code=None,
                message=initial_message,
                log_path=str(log_path),
            )
            self.jobs[job_id] = job
            self.active_job_id = job_id
            asyncio.create_task(self._run_job(job_id, args, stdin_text))
            return job

    async def _run_job(self, job_id: str, args: list[str], stdin_text: str | None) -> None:
        job = self.jobs[job_id]
        job.status = "running"
        job.message = "Starting Codex authentication..."
        try:
            process = await asyncio.create_subprocess_exec(
                *args,
                stdin=asyncio.subprocess.PIPE if stdin_text is not None else None,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                creationflags=_creationflags(),
            )
        except OSError as exc:
            job.status = "failed"
            job.finished_at = _utc_now()
            job.message = str(exc)
            self.active_job_id = None
            return

        async def read_stream(stream: asyncio.StreamReader | None) -> list[str]:
            lines: list[str] = []
            if stream is None:
                return lines
            while True:
                line = await stream.readline()
                if not line:
                    break
                text = line.decode("utf-8", errors="ignore").strip()
                if text:
                    lines.append(text)
                    job.output_lines = (job.output_lines + [text])[-20:]
                    job.message = text
            return lines

        stdout_task = asyncio.create_task(read_stream(process.stdout))
        stderr_task = asyncio.create_task(read_stream(process.stderr))
        if stdin_text is not None and process.stdin is not None:
            process.stdin.write(stdin_text.encode("utf-8"))
            await process.stdin.drain()
            process.stdin.close()

        stdout_lines, stderr_lines = await asyncio.gather(stdout_task, stderr_task)
        job.exit_code = await process.wait()
        job.finished_at = _utc_now()
        combined = [*stdout_lines, *stderr_lines]
        if not combined:
            combined = [job.message]
        Path(job.log_path or "").write_text("\n".join(combined), encoding="utf-8")

        status = detect_codex_status()
        job.auth_mode_after = status.get("auth_mode")
        if job.exit_code == 0:
            job.status = "succeeded"
            if job.method == "logout":
                job.message = "Signed out of the local Codex CLI session."
            else:
                job.message = combined[-1] if combined else "Codex authentication finished."
        else:
            job.status = "failed"
            job.message = combined[-1] if combined else "Codex authentication failed."
        self.active_job_id = None


auth_service = CodexAuthService()
