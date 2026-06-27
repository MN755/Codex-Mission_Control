from __future__ import annotations

from dataclasses import asdict, dataclass

from sqlalchemy.orm import Session

from config import DEFAULT_APPROVAL_POLICY, DEFAULT_CLI_MODEL, DEFAULT_RUNNER_MODE, DEFAULT_SANDBOX
from models import Agent, Project, ProjectSettings
from provider_adapter_recipes import resolve_adapter_recipe
from provider_support import default_label, normalize_provider, provider_label, provider_uses_endpoint
from schemas import ProjectSettingsUpdate
from widget_catalog import validate_widget_types


@dataclass
class ResolvedRunSettings:
    provider: str
    provider_label: str
    runner_mode: str
    sandbox_mode: str
    approval_policy: str
    model: str | None
    reasoning_effort: str | None
    provider_endpoint: str | None
    adapter_command: str | None
    adapter_args: list[str]
    effective_model_label: str
    effective_reasoning_label: str
    remote_execution: dict | None = None


DEFAULT_CODEX_MANAGER_MODEL = DEFAULT_CLI_MODEL
DEFAULT_CODEX_WORKER_MODEL = "gpt-5.4-mini"
DEFAULT_LAUNCH_GUARD_ENABLED = True
DEFAULT_HARD_TOTAL_TOKEN_BUDGET = 2_500_000
DEFAULT_HARD_TOTAL_WORKER_LAUNCH_BUDGET = 120
DEFAULT_HARD_PEAK_CONTEXT_BUDGET = 400_000
DEFAULT_QUOTA_BACKOFF_COOLDOWN_MINUTES = 60

_CODEX_MANAGER_MODEL_ALIASES: dict[str, str] = {
    "gpt54": "gpt-5.4",
    "gpt54medium": "gpt-5.4",
    "gpt54mini": "gpt-5.4-mini",
    "gpt54small": "gpt-5.4-mini",
}
_CODEX_WORKER_MODEL_ALIASES: dict[str, str] = {
    "gpt54mini": DEFAULT_CODEX_WORKER_MODEL,
}


def _normalize_model_key(value: str | None) -> str:
    return "".join(ch for ch in str(value or "").strip().lower() if ch.isalnum())


def normalize_codex_manager_model(value: str | None) -> str | None:
    normalized = normalize_optional_text(value)
    if normalized is None:
        return None
    return _CODEX_MANAGER_MODEL_ALIASES.get(_normalize_model_key(normalized), DEFAULT_CODEX_MANAGER_MODEL)


def normalize_codex_worker_model(value: str | None) -> str | None:
    normalized = normalize_optional_text(value)
    if normalized is None:
        return None
    return _CODEX_WORKER_MODEL_ALIASES.get(_normalize_model_key(normalized), DEFAULT_CODEX_WORKER_MODEL)


def _normalize_per_role_model_overrides(provider: str, overrides: dict[str, str] | None) -> dict[str, str]:
    cleaned: dict[str, str] = {}
    for raw_key, raw_value in (overrides or {}).items():
        key = str(raw_key or "").strip()
        if not key:
            continue
        value = normalize_optional_text(raw_value)
        if value is None:
            continue
        if normalize_provider(provider) == "codex":
            value = normalize_codex_worker_model(value)
        cleaned[key] = value
    return cleaned


def clamp_codex_model_settings(
    provider: str,
    *,
    manager_model: str | None,
    default_worker_model: str | None,
    per_role_model_overrides: dict[str, str] | None,
) -> tuple[str | None, str | None, dict[str, str]]:
    normalized_provider = normalize_provider(provider)
    if normalized_provider != "codex":
        return (
            normalize_optional_text(manager_model),
            normalize_optional_text(default_worker_model),
            _normalize_per_role_model_overrides(normalized_provider, per_role_model_overrides),
        )
    return (
        normalize_codex_manager_model(manager_model),
        normalize_codex_worker_model(default_worker_model),
        _normalize_per_role_model_overrides(normalized_provider, per_role_model_overrides),
    )


def normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def default_model_for_provider(provider: str, *, role: str = "manager") -> str | None:
    normalized = normalize_provider(provider)
    if normalized == "codex":
        return DEFAULT_CODEX_WORKER_MODEL if role == "worker" else DEFAULT_CODEX_MANAGER_MODEL
    return None


def normalize_provider_endpoint(provider: str, value: str | None) -> str | None:
    normalized_provider = normalize_provider(provider)
    if not provider_uses_endpoint(normalized_provider):
        return None
    return normalize_optional_text(value)


def normalize_provider_adapter_command(provider: str, value: str | None) -> str | None:
    recipe = resolve_adapter_recipe(provider, value, None)
    return recipe.command if recipe else None


def normalize_provider_adapter_args(provider: str, values: list[str] | None) -> list[str]:
    recipe = resolve_adapter_recipe(provider, None, values)
    return list(recipe.args) if recipe else []


def normalize_provider_adapter_settings(provider: str, command: str | None, values: list[str] | None) -> tuple[str | None, list[str]]:
    recipe = resolve_adapter_recipe(provider, command, values)
    if recipe is None:
        return None, []
    return recipe.command, list(recipe.args)


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
        launch_guard_enabled=DEFAULT_LAUNCH_GUARD_ENABLED,
        hard_total_token_budget=DEFAULT_HARD_TOTAL_TOKEN_BUDGET,
        hard_total_worker_launch_budget=DEFAULT_HARD_TOTAL_WORKER_LAUNCH_BUDGET,
        hard_peak_context_budget=DEFAULT_HARD_PEAK_CONTEXT_BUDGET,
        quota_backoff_cooldown_minutes=DEFAULT_QUOTA_BACKOFF_COOLDOWN_MINUTES,
        per_role_model_overrides_json={},
        per_role_reasoning_overrides_json={},
        provider_endpoint=None,
        adapter_args_json=[],
        remote_execution_policy_json={},
        workspace_widgets_json=[],
        approval_overrides_json={},
    )
    db.add(settings)
    db.flush()
    project.settings = settings
    return settings


def update_project_settings(db: Session, project: Project, payload: ProjectSettingsUpdate) -> ProjectSettings:
    settings = get_or_create_project_settings(db, project)
    updates = payload.model_dump(exclude_unset=True)
    fields_set = set(getattr(payload, "model_fields_set", set(updates.keys())))

    provider_changed = "provider" in fields_set and payload.provider is not None
    if provider_changed:
        settings.provider = normalize_provider(payload.provider)
    if "manager_model" in fields_set:
        settings.manager_model = normalize_optional_text(payload.manager_model)
    if "default_worker_model" in fields_set:
        settings.default_worker_model = normalize_optional_text(payload.default_worker_model)
    if "manager_reasoning_effort" in fields_set:
        settings.manager_reasoning_effort = payload.manager_reasoning_effort
    if "default_worker_reasoning_effort" in fields_set:
        settings.default_worker_reasoning_effort = payload.default_worker_reasoning_effort
    if "per_role_model_overrides_json" in fields_set and payload.per_role_model_overrides_json is not None:
        settings.per_role_model_overrides_json = _normalize_per_role_model_overrides(
            settings.provider,
            payload.per_role_model_overrides_json,
        )
    if "per_role_reasoning_overrides_json" in fields_set and payload.per_role_reasoning_overrides_json is not None:
        settings.per_role_reasoning_overrides_json = {
            key: value
            for key, value in payload.per_role_reasoning_overrides_json.items()
            if key.strip() and value
        }

    if provider_changed or "provider_endpoint" in fields_set:
        endpoint_source = payload.provider_endpoint if "provider_endpoint" in fields_set else settings.provider_endpoint
        settings.provider_endpoint = normalize_provider_endpoint(settings.provider, endpoint_source)
    if provider_changed or "adapter_command" in fields_set or "adapter_args_json" in fields_set:
        command_source = payload.adapter_command if "adapter_command" in fields_set else settings.adapter_command
        args_source = payload.adapter_args_json if "adapter_args_json" in fields_set else list(settings.adapter_args_json or [])
        settings.adapter_command, settings.adapter_args_json = normalize_provider_adapter_settings(
            settings.provider,
            command_source,
            args_source,
        )
    if "runner_mode" in fields_set and payload.runner_mode is not None:
        settings.runner_mode = payload.runner_mode
        project.runner_mode = payload.runner_mode
    if "sandbox_mode" in fields_set and payload.sandbox_mode is not None:
        settings.sandbox_mode = payload.sandbox_mode
    if "approval_policy" in fields_set and payload.approval_policy is not None:
        settings.approval_policy = payload.approval_policy
    if "launch_guard_enabled" in fields_set and payload.launch_guard_enabled is not None:
        settings.launch_guard_enabled = bool(payload.launch_guard_enabled)
    if "hard_total_token_budget" in fields_set and payload.hard_total_token_budget is not None:
        settings.hard_total_token_budget = max(1, int(payload.hard_total_token_budget))
    if "hard_total_worker_launch_budget" in fields_set and payload.hard_total_worker_launch_budget is not None:
        settings.hard_total_worker_launch_budget = max(1, int(payload.hard_total_worker_launch_budget))
    if "hard_peak_context_budget" in fields_set and payload.hard_peak_context_budget is not None:
        settings.hard_peak_context_budget = max(1, int(payload.hard_peak_context_budget))
    if "quota_backoff_cooldown_minutes" in fields_set and payload.quota_backoff_cooldown_minutes is not None:
        settings.quota_backoff_cooldown_minutes = max(1, int(payload.quota_backoff_cooldown_minutes))
    if "remote_execution_policy_json" in fields_set and payload.remote_execution_policy_json is not None:
        settings.remote_execution_policy_json = dict(payload.remote_execution_policy_json or {})
    if "workspace_widgets_json" in fields_set and payload.workspace_widgets_json is not None:
        settings.workspace_widgets_json = validate_widget_types(
            payload.workspace_widgets_json,
            scope="project",
            field_name="workspace widgets",
        )
    if "approval_overrides_json" in fields_set and payload.approval_overrides_json is not None:
        settings.approval_overrides_json = dict(payload.approval_overrides_json or {})
    (
        settings.manager_model,
        settings.default_worker_model,
        settings.per_role_model_overrides_json,
    ) = clamp_codex_model_settings(
        settings.provider,
        manager_model=settings.manager_model,
        default_worker_model=settings.default_worker_model,
        per_role_model_overrides=settings.per_role_model_overrides_json,
    )
    db.flush()
    return settings


def settings_summary(settings: ProjectSettings) -> dict:
    manager_model, default_worker_model, per_role_model_overrides = clamp_codex_model_settings(
        settings.provider,
        manager_model=settings.manager_model,
        default_worker_model=settings.default_worker_model,
        per_role_model_overrides=settings.per_role_model_overrides_json,
    )
    return {
        "project_id": settings.project_id,
        "provider": normalize_provider(settings.provider),
        "manager_model": manager_model,
        "default_worker_model": default_worker_model,
        "manager_reasoning_effort": settings.manager_reasoning_effort,
        "default_worker_reasoning_effort": settings.default_worker_reasoning_effort,
        "per_role_model_overrides_json": per_role_model_overrides,
        "per_role_reasoning_overrides_json": settings.per_role_reasoning_overrides_json or {},
        "provider_endpoint": settings.provider_endpoint,
        "adapter_command": settings.adapter_command,
        "adapter_args_json": settings.adapter_args_json or [],
        "runner_mode": settings.runner_mode,
        "sandbox_mode": settings.sandbox_mode,
        "approval_policy": settings.approval_policy,
        "launch_guard_enabled": settings.launch_guard_enabled,
        "hard_total_token_budget": settings.hard_total_token_budget,
        "hard_total_worker_launch_budget": settings.hard_total_worker_launch_budget,
        "hard_peak_context_budget": settings.hard_peak_context_budget,
        "quota_backoff_cooldown_minutes": settings.quota_backoff_cooldown_minutes,
        "remote_execution_policy_json": settings.remote_execution_policy_json or {},
        "workspace_widgets_json": settings.workspace_widgets_json or [],
        "approval_overrides_json": settings.approval_overrides_json or {},
        "created_at": settings.created_at,
        "updated_at": settings.updated_at,
    }


def resolve_manager_settings(project: Project, settings: ProjectSettings) -> ResolvedRunSettings:
    provider = normalize_provider(settings.provider)
    model = (
        normalize_codex_manager_model(settings.manager_model)
        if provider == "codex"
        else normalize_optional_text(settings.manager_model)
    ) or default_model_for_provider(provider, role="manager")
    reasoning = settings.manager_reasoning_effort
    adapter_command, adapter_args = normalize_provider_adapter_settings(provider, settings.adapter_command, list(settings.adapter_args_json or []))
    return ResolvedRunSettings(
        provider=provider,
        provider_label=provider_label(provider),
        runner_mode=settings.runner_mode or project.runner_mode or DEFAULT_RUNNER_MODE,
        sandbox_mode=settings.sandbox_mode or DEFAULT_SANDBOX,
        approval_policy=settings.approval_policy or DEFAULT_APPROVAL_POLICY,
        model=model,
        reasoning_effort=reasoning,
        provider_endpoint=normalize_provider_endpoint(provider, settings.provider_endpoint),
        adapter_command=adapter_command,
        adapter_args=adapter_args,
        remote_execution=dict(settings.remote_execution_policy_json or {}),
        effective_model_label=model or default_label(provider),
        effective_reasoning_label=reasoning or default_label(provider),
    )


def resolve_default_worker_settings(project: Project, settings: ProjectSettings) -> ResolvedRunSettings:
    provider = normalize_provider(settings.provider)
    model = (
        normalize_codex_worker_model(settings.default_worker_model)
        if provider == "codex"
        else normalize_optional_text(settings.default_worker_model)
    ) or default_model_for_provider(provider, role="worker")
    reasoning = settings.default_worker_reasoning_effort
    adapter_command, adapter_args = normalize_provider_adapter_settings(provider, settings.adapter_command, list(settings.adapter_args_json or []))
    return ResolvedRunSettings(
        provider=provider,
        provider_label=provider_label(provider),
        runner_mode=settings.runner_mode or project.runner_mode or DEFAULT_RUNNER_MODE,
        sandbox_mode=settings.sandbox_mode or DEFAULT_SANDBOX,
        approval_policy=settings.approval_policy or DEFAULT_APPROVAL_POLICY,
        model=model,
        reasoning_effort=reasoning,
        provider_endpoint=normalize_provider_endpoint(provider, settings.provider_endpoint),
        adapter_command=adapter_command,
        adapter_args=adapter_args,
        remote_execution=dict(settings.remote_execution_policy_json or {}),
        effective_model_label=model or default_label(provider),
        effective_reasoning_label=reasoning or default_label(provider),
    )


def resolve_worker_settings(project: Project, settings: ProjectSettings, agent: Agent) -> ResolvedRunSettings:
    provider = normalize_provider(settings.provider)
    role_key = agent.role
    override_model = normalize_optional_text((settings.per_role_model_overrides_json or {}).get(role_key))
    if provider == "codex":
        override_model = normalize_codex_worker_model(override_model)
    override_reasoning = (settings.per_role_reasoning_overrides_json or {}).get(role_key)
    model = override_model or resolve_default_worker_settings(project, settings).model
    reasoning = override_reasoning or settings.default_worker_reasoning_effort
    adapter_command, adapter_args = normalize_provider_adapter_settings(provider, settings.adapter_command, list(settings.adapter_args_json or []))
    return ResolvedRunSettings(
        provider=provider,
        provider_label=provider_label(provider),
        runner_mode=settings.runner_mode or project.runner_mode or DEFAULT_RUNNER_MODE,
        sandbox_mode=settings.sandbox_mode or DEFAULT_SANDBOX,
        approval_policy=settings.approval_policy or DEFAULT_APPROVAL_POLICY,
        model=model,
        reasoning_effort=reasoning,
        provider_endpoint=normalize_provider_endpoint(provider, settings.provider_endpoint),
        adapter_command=adapter_command,
        adapter_args=adapter_args,
        remote_execution=dict(settings.remote_execution_policy_json or {}),
        effective_model_label=model or default_label(provider),
        effective_reasoning_label=reasoning or default_label(provider),
    )


def resolved_run_settings_payload(resolved: ResolvedRunSettings) -> dict:
    return asdict(resolved)
