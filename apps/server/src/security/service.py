from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import ApprovalAuditLog, Project, RiskAssessment, SecurityPolicy, utc_now

from .redaction import redact_text, redact_value
from .risk_classifier import risk_classifier


DEFAULT_SECURITY_POLICY = {
    "default_command_policy": "ask",
    "default_tool_policy": "ask",
    "network_access_policy": "ask",
    "write_access_policy": "workspace_write",
    "external_account_policy": "ask",
    "deployment_policy": "deny",
    "destructive_action_policy": "critical_approval",
    "auto_approve_low_risk": False,
    "auto_approve_medium_risk": False,
    "high_risk_requires_user": True,
}


class SecurityService:
    def get_policy(self, db: Session, *, project: Project | None = None) -> SecurityPolicy:
        scope = "project" if project is not None else "global"
        query = select(SecurityPolicy).where(SecurityPolicy.scope == scope)
        if project is None:
            query = query.where(SecurityPolicy.project_id.is_(None))
        else:
            query = query.where(SecurityPolicy.project_id == project.id)
        record = db.scalar(query.order_by(SecurityPolicy.id.asc()))
        if record is None:
            record = SecurityPolicy(scope=scope, project_id=project.id if project is not None else None, **DEFAULT_SECURITY_POLICY)
            db.add(record)
            db.flush()
        return record

    def update_policy(self, db: Session, payload: dict[str, Any], *, project: Project | None = None) -> SecurityPolicy:
        record = self.get_policy(db, project=project)
        for key in DEFAULT_SECURITY_POLICY:
            if key in payload and payload[key] is not None:
                setattr(record, key, payload[key])
        record.updated_at = utc_now()
        db.flush()
        return record

    def assess_risk(self, db: Session, payload: dict[str, Any], *, project: Project | None = None) -> RiskAssessment:
        normalized = risk_classifier.classify({**payload, "project_id": project.id if project is not None else payload.get("project_id")})
        record = RiskAssessment(
            project_id=project.id if project is not None else normalized.get("project_id"),
            action_type=normalized["action_type"],
            title=redact_text(normalized["title"]),
            summary=redact_text(normalized["summary"]),
            risk_level=normalized["risk_level"],
            reasons_json=list(normalized["reasons_json"]),
            affected_paths_json=list(normalized["affected_paths_json"]),
            external_access_json=redact_value(normalized["external_access_json"]),
            recommended_policy=normalized["recommended_policy"],
        )
        db.add(record)
        db.flush()
        return record

    def evaluate_action(self, db: Session, payload: dict[str, Any], *, project: Project | None = None) -> dict[str, Any]:
        policy = self.get_policy(db, project=project)
        assessment = self.assess_risk(db, payload, project=project)
        risk_level = assessment.risk_level
        action_type = assessment.action_type
        external_access = dict(assessment.external_access_json or {})
        decision = "pending"
        reason = "User approval is required by default."

        if external_access.get("writes_outside_workspace"):
            decision = "blocked"
            reason = "Policy blocks writes outside the project workspace."
        elif external_access.get("accesses_credentials"):
            decision = "blocked"
            reason = "Policy blocks direct credential or secret access."
        elif external_access.get("deploys") and policy.deployment_policy == "deny":
            decision = "blocked"
            reason = "Deployment actions are denied by policy."
        elif external_access.get("external_access_requested") and action_type in {"connected_account", "plugin"} and policy.external_account_policy == "deny":
            decision = "blocked"
            reason = "Connected accounts and plugin side effects are denied by policy."
        elif external_access.get("accesses_network") and policy.network_access_policy == "deny":
            decision = "blocked"
            reason = "Network access is denied by policy."
        elif risk_level == "critical" and policy.destructive_action_policy == "deny":
            decision = "blocked"
            reason = "Critical destructive actions are denied by policy."
        elif risk_level in {"high", "critical"} and policy.high_risk_requires_user:
            decision = "pending"
            reason = "High-risk actions require explicit user approval."
        elif risk_level == "low" and policy.default_command_policy == "allow_low_risk" and policy.auto_approve_low_risk:
            decision = "auto_approved"
            reason = "Low-risk action matched the current auto-approve policy."
        elif risk_level == "low" and action_type != "command" and policy.default_tool_policy == "allow_low_risk" and policy.auto_approve_low_risk:
            decision = "auto_approved"
            reason = "Low-risk tool action matched the current auto-approve policy."
        elif risk_level == "medium" and policy.auto_approve_medium_risk and action_type == "command" and policy.default_command_policy == "allow_low_risk":
            decision = "auto_approved"
            reason = "Medium-risk command matched the configured auto-approve policy."

        return {
            "policy": record_to_dict(policy),
            "assessment": record_to_dict(assessment),
            "decision": decision,
            "reason": reason,
        }

    def log_audit(
        self,
        db: Session,
        *,
        project: Project | None = None,
        orchestration_id: int | None = None,
        decision_id: int | None = None,
        action_type: str,
        action_summary: str,
        risk_level: str,
        decision: str,
        decided_by: str,
        reason: str,
        metadata_json: dict[str, Any] | None = None,
    ) -> ApprovalAuditLog:
        record = ApprovalAuditLog(
            project_id=project.id if project is not None else None,
            orchestration_id=orchestration_id,
            decision_id=decision_id,
            action_type=action_type,
            action_summary=redact_text(action_summary),
            risk_level=risk_level,
            decision=decision,
            decided_by=decided_by,
            reason=redact_text(reason),
            metadata_json=redact_value(metadata_json or {}),
        )
        db.add(record)
        db.flush()
        return record

    def list_audit_logs(self, db: Session, *, project: Project | None = None) -> list[ApprovalAuditLog]:
        query = select(ApprovalAuditLog)
        if project is not None:
            query = query.where(ApprovalAuditLog.project_id == project.id)
        return list(db.scalars(query.order_by(ApprovalAuditLog.created_at.desc(), ApprovalAuditLog.id.desc())))

    def recent_risk_assessments(self, db: Session, *, project: Project | None = None) -> list[RiskAssessment]:
        query = select(RiskAssessment)
        if project is not None:
            query = query.where(RiskAssessment.project_id == project.id)
        return list(db.scalars(query.order_by(RiskAssessment.created_at.desc(), RiskAssessment.id.desc())))

    @staticmethod
    def may_allow_for_project(risk_level: str) -> bool:
        return risk_level in {"low", "medium"}


def record_to_dict(record: Any) -> dict[str, Any]:
    return {column.name: getattr(record, column.name) for column in record.__table__.columns}


security_service = SecurityService()
