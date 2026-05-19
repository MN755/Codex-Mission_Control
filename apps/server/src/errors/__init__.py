from errors.breakpoints import BREAKPOINT_DESCRIPTIONS
from errors.codes import ERROR_CODE_PATTERN, docs_anchor_for_code, is_valid_error_code
from errors.families import ERROR_FAMILY_DESCRIPTIONS
from errors.formatting import (
    derive_health_status,
    format_codex_chat_error,
    format_diagnostic_report_item,
    format_health_check_item,
    format_install_report_item,
    format_log_event,
    format_problem_details,
)
from errors.problem import MissionControlError, as_mission_control_error
from errors.registry import ERROR_REGISTRY, ErrorDefinition, get_error_definition, iter_error_definitions
from errors.severity import HEALTH_STATUS_BY_SEVERITY, SEVERITY_LEVELS, USER_STATUS_BY_SEVERITY

__all__ = [
    "BREAKPOINT_DESCRIPTIONS",
    "ERROR_CODE_PATTERN",
    "ERROR_FAMILY_DESCRIPTIONS",
    "ERROR_REGISTRY",
    "ErrorDefinition",
    "HEALTH_STATUS_BY_SEVERITY",
    "MissionControlError",
    "SEVERITY_LEVELS",
    "USER_STATUS_BY_SEVERITY",
    "as_mission_control_error",
    "derive_health_status",
    "docs_anchor_for_code",
    "format_codex_chat_error",
    "format_diagnostic_report_item",
    "format_health_check_item",
    "format_install_report_item",
    "format_log_event",
    "format_problem_details",
    "get_error_definition",
    "is_valid_error_code",
    "iter_error_definitions",
]
