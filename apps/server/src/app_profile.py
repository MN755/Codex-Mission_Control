from __future__ import annotations

import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from config import DEFAULT_APPROVAL_POLICY, DEFAULT_RUNNER_MODE, DEFAULT_SANDBOX
from integration_registry import normalize_integration_registry, registry_to_legacy_connected_accounts
from models import AppProfile, utc_now
from provider_support import normalize_provider
from project_settings import normalize_provider_adapter_settings, normalize_provider_endpoint
from schemas import AppProfileUpdate, CompleteFirstRunRequest
from widget_catalog import validate_widget_types


DEFAULT_DISPLAY_NAME = "Operator"
DEFAULT_THEME = "system"
DEFAULT_STARTUP_BEHAVIOR = "dashboard"
DEFAULT_NOTIFICATION_PREFERENCES = {
    "desktop_toasts": False,
    "sound": False,
    "action_required_only": True,
}


def normalize_display_name(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    return normalized[:50]


def display_name_or_default(value: str | None) -> str:
    return normalize_display_name(value) or DEFAULT_DISPLAY_NAME


def normalize_startup_provider_choice(value: str | None) -> str:
    normalized = normalize_provider(value)
    return normalized


def normalize_theme(value: str | None) -> str:
    if value in {"system", "dark", "light"}:
        return value
    return DEFAULT_THEME


def normalize_startup_behavior(value: str | None) -> str:
    if value in {"dashboard", "last_project", "restore_previous_page"}:
        return value
    return DEFAULT_STARTUP_BEHAVIOR


def _sync_completion_flags(profile: AppProfile) -> None:
    if profile.first_run_completed and not profile.onboarding_completed:
        profile.onboarding_completed = True
    if profile.onboarding_completed and not profile.first_run_completed:
        profile.first_run_completed = True


def get_or_create_app_profile(db: Session) -> AppProfile:
    profile = db.get(AppProfile, 1)
    if profile is not None:
        updated = False
        if not profile.install_id:
            profile.install_id = uuid.uuid4().hex
            updated = True
        if not profile.selected_provider:
            profile.selected_provider = normalize_startup_provider_choice(profile.preferred_provider_choice)
            updated = True
        if not profile.connected_accounts_json:
            profile.connected_accounts_json = {}
            updated = True
        normalized_registry = normalize_integration_registry(
            profile.integration_registry_json,
            profile.connected_accounts_json,
        )
        if dict(profile.integration_registry_json or {}) != normalized_registry:
            profile.integration_registry_json = normalized_registry
            updated = True
        normalized_legacy = registry_to_legacy_connected_accounts(profile.integration_registry_json)
        merged_legacy = dict(normalized_legacy)
        merged_legacy.update({key: value for key, value in dict(profile.connected_accounts_json or {}).items() if key not in merged_legacy})
        if dict(profile.connected_accounts_json or {}) != merged_legacy:
            profile.connected_accounts_json = merged_legacy
            updated = True
        if not profile.adapter_args_json:
            profile.adapter_args_json = []
            updated = True
        if not profile.notification_preferences_json:
            profile.notification_preferences_json = dict(DEFAULT_NOTIFICATION_PREFERENCES)
            updated = True
        if not profile.dashboard_widgets_json:
            profile.dashboard_widgets_json = []
            updated = True
        if not profile.dashboard_widget_preferences_json:
            profile.dashboard_widget_preferences_json = {}
            updated = True
        if not profile.tool_permission_overrides_json:
            profile.tool_permission_overrides_json = {}
            updated = True
        normalized_theme = normalize_theme(profile.theme)
        if profile.theme != normalized_theme:
            profile.theme = normalized_theme
            updated = True
        normalized_startup_behavior = normalize_startup_behavior(profile.startup_behavior)
        if profile.startup_behavior != normalized_startup_behavior:
            profile.startup_behavior = normalized_startup_behavior
            updated = True
        original_first_run = profile.first_run_completed
        original_onboarding = profile.onboarding_completed
        _sync_completion_flags(profile)
        if profile.first_run_completed != original_first_run or profile.onboarding_completed != original_onboarding:
            updated = True
        if updated:
            db.flush()
        return profile
    profile = AppProfile(
        id=1,
        display_name=None,
        install_id=uuid.uuid4().hex,
        preferred_provider_choice="codex",
        preferred_start_mode="new_project",
        selected_provider="codex",
        auth_mode=None,
        connected_accounts_json={},
        integration_registry_json=normalize_integration_registry({}, {}),
        first_run_completed=False,
        setup_version_completed=None,
        onboarding_completed=False,
        default_runner_mode=DEFAULT_RUNNER_MODE,
        manager_model=None,
        default_worker_model=None,
        manager_reasoning_effort=None,
        default_worker_reasoning_effort=None,
        sandbox_mode=DEFAULT_SANDBOX,
        approval_policy=DEFAULT_APPROVAL_POLICY,
        theme=DEFAULT_THEME,
        startup_behavior=DEFAULT_STARTUP_BEHAVIOR,
        notification_preferences_json=dict(DEFAULT_NOTIFICATION_PREFERENCES),
        dashboard_widgets_json=[],
        dashboard_widget_preferences_json={},
        tool_permission_overrides_json={},
        provider_endpoint=None,
        adapter_command=None,
        adapter_args_json=[],
        recent_startup_error_json=None,
        last_opened_at=utc_now(),
    )
    db.add(profile)
    try:
        db.flush()
        return profile
    except IntegrityError:
        db.rollback()
        return get_or_create_app_profile(db)


def update_app_profile(db: Session, payload: AppProfileUpdate) -> AppProfile:
    profile = get_or_create_app_profile(db)
    if payload.display_name is not None:
        profile.display_name = normalize_display_name(payload.display_name)
    if payload.preferred_provider_choice is not None:
        profile.preferred_provider_choice = normalize_startup_provider_choice(payload.preferred_provider_choice)
        profile.selected_provider = normalize_startup_provider_choice(payload.preferred_provider_choice)
    if payload.preferred_start_mode is not None:
        profile.preferred_start_mode = payload.preferred_start_mode
    if payload.onboarding_completed is not None:
        profile.onboarding_completed = payload.onboarding_completed
        profile.first_run_completed = payload.onboarding_completed
    if payload.theme is not None:
        profile.theme = normalize_theme(payload.theme)
    if payload.startup_behavior is not None:
        profile.startup_behavior = normalize_startup_behavior(payload.startup_behavior)
    if payload.notification_preferences_json is not None:
        profile.notification_preferences_json = {
            key: bool(value) for key, value in payload.notification_preferences_json.items() if key.strip()
        } or dict(DEFAULT_NOTIFICATION_PREFERENCES)
    if payload.dashboard_widgets_json is not None:
        profile.dashboard_widgets_json = validate_widget_types(
            payload.dashboard_widgets_json,
            scope="dashboard",
            field_name="dashboard widgets",
        )
    if payload.dashboard_widget_preferences_json is not None:
        profile.dashboard_widget_preferences_json = {
            key: value for key, value in payload.dashboard_widget_preferences_json.items() if key.strip()
        }
    profile.last_opened_at = utc_now()
    db.flush()
    return profile


def complete_first_run(db: Session, payload: CompleteFirstRunRequest, *, setup_version: str) -> AppProfile:
    profile = get_or_create_app_profile(db)
    selected_provider = normalize_startup_provider_choice(payload.provider)
    profile.display_name = normalize_display_name(payload.username)
    profile.preferred_provider_choice = selected_provider
    profile.preferred_start_mode = payload.start_mode or profile.preferred_start_mode
    profile.selected_provider = selected_provider
    profile.auth_mode = payload.auth_mode
    profile.connected_accounts_json = payload.connected_accounts_summary or {}
    profile.integration_registry_json = normalize_integration_registry({}, profile.connected_accounts_json)
    profile.connected_accounts_json = registry_to_legacy_connected_accounts(profile.integration_registry_json) | {
        key: value for key, value in dict(payload.connected_accounts_summary or {}).items() if key not in registry_to_legacy_connected_accounts(profile.integration_registry_json)
    }
    profile.first_run_completed = True
    profile.onboarding_completed = True
    profile.setup_version_completed = setup_version
    profile.default_runner_mode = payload.default_runner_mode or profile.default_runner_mode
    profile.manager_model = payload.manager_model.strip() if payload.manager_model and payload.manager_model.strip() else None
    profile.default_worker_model = (
        payload.default_worker_model.strip() if payload.default_worker_model and payload.default_worker_model.strip() else None
    )
    profile.manager_reasoning_effort = payload.manager_reasoning_effort
    profile.default_worker_reasoning_effort = payload.default_worker_reasoning_effort
    profile.sandbox_mode = payload.sandbox_mode or profile.sandbox_mode
    profile.approval_policy = payload.approval_policy or profile.approval_policy
    profile.provider_endpoint = normalize_provider_endpoint(selected_provider, payload.provider_endpoint)
    profile.adapter_command, profile.adapter_args_json = normalize_provider_adapter_settings(
        selected_provider,
        payload.adapter_command,
        payload.adapter_args,
    )
    profile.recent_startup_error_json = None
    profile.last_opened_at = utc_now()
    db.flush()
    return profile
