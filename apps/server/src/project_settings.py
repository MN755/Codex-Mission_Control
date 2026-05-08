from __future__ import annotations

from dataclasses import asdict, dataclass

from sqlalchemy.orm import Session

from config import DEFAULT_APPROVAL_POLICY, DEFAULT_RUNNER_MODE, DEFAULT_SANDBOX
from models import Agent, Project, ProjectSettings
from provider_support import default_label, normalize_provider, provider_label
from schemas import ProjectSettingsUpdate


@dataclass
class ResolvedRunSettings:
    provider: str
    provider_label: str
    runner_mode: str
    sandbox_mode: str
    approval_policy: str
    model: str | None
    reasoning_effort: str | None
    adapter_command: str | None
    adapter_args: list[str]
    effective_model_label: str
    effective_reasoning_label: str


def normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def get_or_create_project_settings(db: Session, project: Project) -> ProjectSettings:
    settings = project.settings
    if settings is not None:
        return settings
    settings = ProjectSettings(
        project_id=project.id,
        provider="codex",
        runner_mode=project.runner_mode or DEFAULT_RUNNER_MODE,
        sandbox_mode=DEFAULT_SANDBOX,
        approval_policy=DEFAULT_APPROVAL_POLICY,
        per_role_model_overrides_json={},
        per_role_reasoning_overrides_json={},
        adapter_args_json=[],
    )
    db.add(settings)
    db.flush()
    project.settings = settings
    return settings


def update_project_settings(db: Session, project: Project, payload: ProjectSettingsUpdate) -> ProjectSettings:
    settings = get_or_create_project_settings(db, project)
    settings.provider = normalize_provider(payload.provider)
    settings.manager_model = normalize_optional_text(payload.manager_model)
    settings.default_worker_model = normalize_optional_text(payload.default_worker_model)
    settings.manager_reasoning_effort = payload.manager_reasoning_effort
    settings.default_worker_reasoning_effort = payload.default_worker_reasoning_effort
    settings.per_role_model_overrides_json = {
        key: value.strip()
        for key, value in payload.per_role_model_overrides_json.items()
        if key.strip() and value.strip()
    }
    settings.per_role_reasoning_overrides_json = {
        key: value
        for key, value in payload.per_role_reasoning_overrides_json.items()
        if key.strip() and value
    }
    settings.adapter_command = normalize_optional_text(payload.adapter_command)
    settings.adapter_args_json = [item.strip() for item in payload.adapter_args_json if item and item.strip()]
    settings.runner_mode = payload.runner_mode
    settings.sandbox_mode = payload.sandbox_mode
    settings.approval_policy = payload.approval_policy
    project.runner_mode = payload.runner_mode
    db.flush()
    return settings


def settings_summary(settings: ProjectSettings) -> dict:
    return {
        "project_id": settings.project_id,
        "provider": normalize_provider(settings.provider),
        "manager_model": settings.manager_model,
        "default_worker_model": settings.default_worker_model,
        "manager_reasoning_effort": settings.manager_reasoning_effort,
        "default_worker_reasoning_effort": settings.default_worker_reasoning_effort,
        "per_role_model_overrides_json": settings.per_role_model_overrides_json or {},
        "per_role_reasoning_overrides_json": settings.per_role_reasoning_overrides_json or {},
        "adapter_command": settings.adapter_command,
        "adapter_args_json": settings.adapter_args_json or [],
        "runner_mode": settings.runner_mode,
        "sandbox_mode": settings.sandbox_mode,
        "approval_policy": settings.approval_policy,
        "created_at": settings.created_at,
        "updated_at": settings.updated_at,
    }


def resolve_manager_settings(project: Project, settings: ProjectSettings) -> ResolvedRunSettings:
    provider = normalize_provider(settings.provider)
    model = normalize_optional_text(settings.manager_model)
    reasoning = settings.manager_reasoning_effort
    return ResolvedRunSettings(
        provider=provider,
        provider_label=provider_label(provider),
        runner_mode=settings.runner_mode or project.runner_mode or DEFAULT_RUNNER_MODE,
        sandbox_mode=settings.sandbox_mode or DEFAULT_SANDBOX,
        approval_policy=settings.approval_policy or DEFAULT_APPROVAL_POLICY,
        model=model,
        reasoning_effort=reasoning,
        adapter_command=normalize_optional_text(settings.adapter_command),
        adapter_args=list(settings.adapter_args_json or []),
        effective_model_label=model or default_label(provider),
        effective_reasoning_label=reasoning or default_label(provider),
    )


def resolve_worker_settings(project: Project, settings: ProjectSettings, agent: Agent) -> ResolvedRunSettings:
    provider = normalize_provider(settings.provider)
    role_key = agent.role
    override_model = normalize_optional_text((settings.per_role_model_overrides_json or {}).get(role_key))
    override_reasoning = (settings.per_role_reasoning_overrides_json or {}).get(role_key)
    model = override_model or normalize_optional_text(settings.default_worker_model)
    reasoning = override_reasoning or settings.default_worker_reasoning_effort
    return ResolvedRunSettings(
        provider=provider,
        provider_label=provider_label(provider),
        runner_mode=settings.runner_mode or project.runner_mode or DEFAULT_RUNNER_MODE,
        sandbox_mode=settings.sandbox_mode or DEFAULT_SANDBOX,
        approval_policy=settings.approval_policy or DEFAULT_APPROVAL_POLICY,
        model=model,
        reasoning_effort=reasoning,
        adapter_command=normalize_optional_text(settings.adapter_command),
        adapter_args=list(settings.adapter_args_json or []),
        effective_model_label=model or default_label(provider),
        effective_reasoning_label=reasoning or default_label(provider),
    )


def resolved_run_settings_payload(resolved: ResolvedRunSettings) -> dict:
    return asdict(resolved)
