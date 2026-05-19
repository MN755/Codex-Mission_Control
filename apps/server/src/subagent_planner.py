from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from bridge_formatter import format_pending_decision_message
from manager import service
from models import PendingDecision, Project, SubagentBatch, SubagentPolicy, SubagentSpec, utc_now


DEFAULT_ALLOWED_TASK_TYPES = [
    "codebase_exploration",
    "review",
    "planning",
    "handoff_audit",
    "failure_diagnosis",
]

DEFAULT_TEMPLATE_BY_TASK_TYPE = {
    "codebase_exploration": "codebase_intake_burst",
    "review": "review_burst",
    "planning": "planning_burst",
    "failure_diagnosis": "failure_diagnosis_burst",
    "handoff_audit": "handoff_audit_burst",
}


@dataclass(frozen=True)
class BurstSpecTemplate:
    name: str
    display_name: str
    custom_agent_name: str | None
    mission: str
    expected_output: str
    default_timeout_seconds: int


def _spec(
    name: str,
    display_name: str,
    custom_agent_name: str | None,
    mission: str,
    expected_output: str,
    default_timeout_seconds: int = 240,
) -> BurstSpecTemplate:
    return BurstSpecTemplate(
        name=name,
        display_name=display_name,
        custom_agent_name=custom_agent_name,
        mission=mission,
        expected_output=expected_output,
        default_timeout_seconds=default_timeout_seconds,
    )


BURST_TEMPLATES: dict[str, dict[str, Any]] = {
    "codebase_intake_burst": {
        "purpose": "Read-only codebase intake",
        "task_type": "codebase_exploration",
        "subagents": [
            _spec("repo_mapper", "Repo Mapper", "mc-repo-mapper", "Map the repo structure, entry points, and ownership boundaries.", "Return a compact repo map with major folders, entry points, and likely seams."),
            _spec("test_finder", "Test Finder", "mc-test-finder", "Find test suites, validation commands, and coverage blind spots.", "Return test locations, likely commands, and obvious missing coverage areas."),
            _spec("docs_reader", "Docs Reader", "mc-docs-reader", "Read existing docs, AGENTS.md, and operational notes.", "Return doc inventory, stale areas, and high-signal guidance for new contributors."),
            _spec("risk_scanner", "Risk Scanner", "mc-risk-scanner", "Identify high-risk areas, destructive surfaces, and fragile integrations.", "Return risk hotspots and why they matter for future work."),
            _spec("dependency_mapper", "Dependency Mapper", "mc-dependency-mapper", "Map package managers, major dependencies, and integration boundaries.", "Return dependency surfaces, major packages, and coupling risks."),
        ],
    },
    "review_burst": {
        "purpose": "Read-only multi-angle review",
        "task_type": "review",
        "subagents": [
            _spec("correctness_reviewer", "Correctness Reviewer", "mc-correctness-reviewer", "Review logic paths for likely bugs or behavioral regressions.", "Return concrete correctness findings with cited files."),
            _spec("security_reviewer", "Security Reviewer", "mc-security-reviewer", "Review for secret exposure, unsafe execution, and trust-boundary issues.", "Return concrete security findings with severity and file citations."),
            _spec("test_coverage_reviewer", "Test Coverage Reviewer", "mc-test-coverage-reviewer", "Review whether the current changes are validated well enough.", "Return likely missing tests and validation gaps."),
            _spec("maintainability_reviewer", "Maintainability Reviewer", "mc-maintainability-reviewer", "Review readability, complexity, and long-term maintenance risks.", "Return maintainability risks and refactor pressure points."),
            _spec("docs_reviewer", "Docs Reviewer", None, "Review docs and operator guidance for accuracy and gaps.", "Return missing or stale docs that could mislead operators."),
        ],
    },
    "planning_burst": {
        "purpose": "Parallel planning pass",
        "task_type": "planning",
        "subagents": [
            _spec("architecture_planner", "Architecture Planner", None, "Plan architectural changes and dependency boundaries.", "Return a proposed architecture direction and main tradeoffs."),
            _spec("frontend_impact_planner", "Frontend Impact Planner", None, "Estimate frontend-facing impact without editing UI files.", "Return affected surfaces, risks, and likely constraints."),
            _spec("backend_impact_planner", "Backend Impact Planner", None, "Estimate backend and orchestration impact.", "Return affected services, data flows, and API implications."),
            _spec("testing_planner", "Testing Planner", None, "Plan validation, regression, and confidence-building steps.", "Return validation strategy and likely evidence requirements."),
            _spec("risk_planner", "Risk Planner", None, "Plan risk mitigations, approvals, and rollback posture.", "Return top risks and mitigation sequence."),
        ],
    },
    "failure_diagnosis_burst": {
        "purpose": "Read-only failure diagnosis",
        "task_type": "failure_diagnosis",
        "subagents": [
            _spec("logs_analyst", "Logs Analyst", None, "Read safe logs and event summaries for failure clues.", "Return likely failure signatures and supporting evidence."),
            _spec("recent_changes_analyst", "Recent Changes Analyst", None, "Inspect recent project changes and likely regression points.", "Return recent-change suspects and why they matter."),
            _spec("test_failure_analyst", "Test Failure Analyst", None, "Analyze failing tests or validation evidence.", "Return likely root-cause clusters and missing evidence."),
            _spec("dependency_analyst", "Dependency Analyst", None, "Analyze dependency or environment drift as a failure source.", "Return dependency and environment suspects."),
            _spec("recovery_planner", "Recovery Planner", None, "Suggest bounded recovery options from the evidence.", "Return recovery options with risk and confidence."),
        ],
    },
    "handoff_audit_burst": {
        "purpose": "Read-only handoff audit",
        "task_type": "handoff_audit",
        "subagents": [
            _spec("run_instructions_auditor", "Run Instructions Auditor", "mc-handoff-auditor", "Audit whether run instructions are complete and believable.", "Return gaps or ambiguity in run instructions."),
            _spec("validation_evidence_auditor", "Validation Evidence Auditor", None, "Audit whether validation claims are supported by evidence.", "Return weak evidence or unsupported claims."),
            _spec("known_limitations_auditor", "Known Limitations Auditor", None, "Audit whether known limitations are honest and complete.", "Return hidden or under-described limitations."),
            _spec("docs_quality_auditor", "Docs Quality Auditor", None, "Audit handoff docs for clarity and operator usefulness.", "Return doc quality issues that hurt handoff reliability."),
            _spec("security_caveat_auditor", "Security Caveat Auditor", None, "Audit whether security caveats are surfaced clearly.", "Return missing security caveats or unsafe omissions."),
        ],
    },
}


CUSTOM_AGENT_LIBRARY = {
    "mc-repo-mapper": _spec("repo_mapper", "Repo Mapper", "mc-repo-mapper", "Map repo structure and seams.", "Report folders, entry points, and repo shape."),
    "mc-test-finder": _spec("test_finder", "Test Finder", "mc-test-finder", "Find tests and validation commands.", "Report tests, likely commands, and coverage blind spots."),
    "mc-docs-reader": _spec("docs_reader", "Docs Reader", "mc-docs-reader", "Read docs and agent guidance.", "Report doc inventory, stale docs, and important guidance."),
    "mc-risk-scanner": _spec("risk_scanner", "Risk Scanner", "mc-risk-scanner", "Identify fragile or risky areas.", "Report risk hotspots and operator concerns."),
    "mc-dependency-mapper": _spec("dependency_mapper", "Dependency Mapper", "mc-dependency-mapper", "Map major dependencies and integration points.", "Report packages, integrations, and dependency risks."),
    "mc-correctness-reviewer": _spec("correctness_reviewer", "Correctness Reviewer", "mc-correctness-reviewer", "Review correctness and regression risks.", "Report correctness findings with file citations."),
    "mc-security-reviewer": _spec("security_reviewer", "Security Reviewer", "mc-security-reviewer", "Review security boundaries and secret handling.", "Report concrete security findings with severity."),
    "mc-test-coverage-reviewer": _spec("test_coverage_reviewer", "Test Coverage Reviewer", "mc-test-coverage-reviewer", "Review validation sufficiency.", "Report missing tests and thin evidence."),
    "mc-maintainability-reviewer": _spec("maintainability_reviewer", "Maintainability Reviewer", "mc-maintainability-reviewer", "Review maintainability and complexity.", "Report readability and maintenance risks."),
    "mc-handoff-auditor": _spec("handoff_auditor", "Handoff Auditor", "mc-handoff-auditor", "Audit handoff quality and operator confidence.", "Report handoff weaknesses and confidence gaps."),
}


class SubagentPlannerService:
    def ensure_policy(self, db: Session) -> SubagentPolicy:
        policy = db.get(SubagentPolicy, 1)
        if policy is None:
            policy = SubagentPolicy(
                id=1,
                enabled=True,
                default_mode="read_only",
                max_subagents_per_burst=6,
                max_runtime_seconds=600,
                allow_file_edits=False,
                allow_commands=False,
                require_user_approval_above_count=3,
                allowed_task_types_json=list(DEFAULT_ALLOWED_TASK_TYPES),
                default_spawn_method="codex_chat_bridge",
            )
            db.add(policy)
            db.flush()
        return policy

    def update_policy(self, db: Session, updates: dict[str, Any]) -> SubagentPolicy:
        policy = self.ensure_policy(db)
        for key, value in updates.items():
            if value is None or not hasattr(policy, key):
                continue
            setattr(policy, key, value)
        db.flush()
        return policy

    def template_catalog(self) -> dict[str, dict[str, Any]]:
        return BURST_TEMPLATES

    def _project_codebase_size(self, project: Project) -> str:
        codebase_map = getattr(project, "codebase_map", None)
        size = getattr(codebase_map, "codebase_size", None)
        return str(size or "medium")

    def _estimated_intensity(self, *, codebase_size: str, count: int, task_complexity: str) -> str:
        if codebase_size in {"large", "huge"} or count >= 5 or task_complexity == "large":
            return "high" if count >= 5 and codebase_size in {"large", "huge"} else "medium"
        if count <= 2 and task_complexity == "small":
            return "low"
        return "medium"

    def _should_recommend(self, *, task_type: str, codebase_size: str, task_complexity: str, expected_parallelism: int, risk_level: str, bounded_scope: bool, requires_file_edits: bool, requires_commands: bool, policy: SubagentPolicy) -> tuple[bool, str, list[str]]:
        reasons: list[str] = []
        risks: list[str] = []
        if not policy.enabled or policy.default_mode == "disabled":
            return False, "Subagent bursts are disabled by policy.", ["Policy disables subagent bursts."]
        if task_type not in list(policy.allowed_task_types_json or []):
            return False, f"Task type `{task_type}` is not allowed by the subagent policy.", [f"`{task_type}` is outside the allowed task types."]
        if requires_file_edits:
            return False, "This task needs file edits, so the default read-only burst mode is a bad fit.", ["Coordinated edits should stay in the normal worker system."]
        if requires_commands:
            return False, "This task needs command execution, which the default burst policy does not allow.", ["Subagent bursts default to no-command mode."]
        if not bounded_scope:
            return False, "The scope is not bounded enough for a short-lived burst.", ["Unclear scope produces noisy parallel output."]
        if expected_parallelism < 2:
            return False, "The work is too small to justify a burst.", ["Low parallelism is not worth the coordination cost."]
        if task_complexity == "small" and codebase_size == "small":
            return False, "This looks simple enough that a burst would be wasted motion.", ["The coordination overhead outweighs the likely value."]
        if risk_level in {"high", "critical"}:
            risks.append("High-risk work can produce noisy recommendations or duplicate caution without speeding execution.")
        if codebase_size in {"large", "huge"}:
            reasons.append("The codebase has enough surface area to split read-heavy exploration in parallel.")
        if task_type in {"review", "planning", "failure_diagnosis", "handoff_audit"}:
            reasons.append("The task can be decomposed into independent, report-oriented subproblems.")
        if not reasons:
            reasons.append("The task is read-heavy and parallelizable enough to benefit from bounded subagents.")
        return True, " ".join(reasons), risks

    def _serialize_policy(self, policy: SubagentPolicy) -> dict[str, Any]:
        return {
            "id": policy.id,
            "enabled": policy.enabled,
            "default_mode": policy.default_mode,
            "max_subagents_per_burst": policy.max_subagents_per_burst,
            "max_runtime_seconds": policy.max_runtime_seconds,
            "allow_file_edits": policy.allow_file_edits,
            "allow_commands": policy.allow_commands,
            "require_user_approval_above_count": policy.require_user_approval_above_count,
            "allowed_task_types_json": list(policy.allowed_task_types_json or []),
            "default_spawn_method": policy.default_spawn_method,
            "created_at": policy.created_at,
            "updated_at": policy.updated_at,
        }

    def _pending_decision_for_batch(self, db: Session, batch_id: int) -> PendingDecision | None:
        return db.scalar(
            select(PendingDecision)
            .where(PendingDecision.source_kind == "subagent_batch", PendingDecision.source_id == batch_id)
            .order_by(PendingDecision.id.desc())
        )

    def _serialize_spec(self, spec: SubagentSpec) -> dict[str, Any]:
        return {
            "id": spec.id,
            "batch_id": spec.batch_id,
            "name": spec.name,
            "display_name": spec.display_name,
            "custom_agent_name": spec.custom_agent_name,
            "mission": spec.mission,
            "sandbox_mode": spec.sandbox_mode,
            "allowed_paths_json": list(spec.allowed_paths_json or []),
            "forbidden_paths_json": list(spec.forbidden_paths_json or []),
            "expected_output": spec.expected_output,
            "timeout_seconds": spec.timeout_seconds,
            "status": spec.status,
            "result_summary": spec.result_summary,
            "evidence_json": list(spec.evidence_json or []),
            "risks_found_json": list(spec.risks_found_json or []),
            "recommendations_json": list(spec.recommendations_json or []),
            "confidence": spec.confidence,
            "created_at": spec.created_at,
            "completed_at": spec.completed_at,
        }

    def _render_spawn_instructions(self, batch: SubagentBatch) -> str:
        lines = [
            "## Mission Control Codex subagent burst",
            "",
            f"**Purpose:** {batch.purpose}",
            f"**Spawn method:** {batch.spawn_method}",
            f"**Read-only default:** yes",
            f"**Commands allowed:** no",
            "",
            "### Proposed subagents",
        ]
        for spec in batch.specs:
            lines.extend(
                [
                    f"- **{spec.display_name}**",
                    f"  Mission: {spec.mission}",
                    f"  Expected output: {spec.expected_output}",
                    f"  Timeout: {spec.timeout_seconds}s",
                ]
            )
        return "\n".join(lines)

    def _render_manual_prompt(self, batch: SubagentBatch) -> str:
        lines = [
            "Spawn short-lived Codex subagents for the following read-only tasks.",
            "Do not edit files. Do not run commands. Do not delegate recursively. Stop at depth 1.",
            "",
        ]
        for spec in batch.specs:
            lines.extend(
                [
                    f"Subagent: {spec.display_name}",
                    f"Mission: {spec.mission}",
                    f"Expected output: {spec.expected_output}",
                    "---",
                ]
            )
        return "\n".join(lines).strip()

    def _serialize_batch(self, db: Session, batch: SubagentBatch) -> dict[str, Any]:
        decision = self._pending_decision_for_batch(db, batch.id)
        bridge_message = None
        if decision is not None and decision.status == "pending":
            bridge_message = format_pending_decision_message(decision=self._serialize_pending_decision(decision))
        return {
            "id": batch.id,
            "project_id": batch.project_id,
            "orchestration_id": batch.orchestration_id,
            "purpose": batch.purpose,
            "task_type": batch.task_type,
            "status": batch.status,
            "spawn_method": batch.spawn_method,
            "risk_level": batch.risk_level,
            "estimated_intensity": batch.estimated_intensity,
            "reason": batch.reason,
            "summary": batch.summary,
            "created_at": batch.created_at,
            "approved_at": batch.approved_at,
            "started_at": batch.started_at,
            "completed_at": batch.completed_at,
            "specs": [self._serialize_spec(spec) for spec in batch.specs],
            "bridge_message": bridge_message,
            "spawn_instructions_markdown": self._render_spawn_instructions(batch),
            "manual_prompt_text": self._render_manual_prompt(batch),
        }

    def _serialize_pending_decision(self, decision: PendingDecision) -> dict[str, Any]:
        options = list(decision.options_json or [])
        presentation = dict(decision.presentation_json or {}) if decision.presentation_json else None
        return {
            "id": decision.id,
            "project_id": decision.project_id,
            "orchestration_id": decision.orchestration_id,
            "decision_type": decision.decision_type,
            "title": decision.title,
            "message": decision.message,
            "requesting_agent_id": decision.requesting_agent_id,
            "related_agent_id": decision.requesting_agent_id,
            "related_task_id": decision.related_task_id,
            "risk_level": decision.risk_level,
            "options": options,
            "options_json": options,
            "recommended_option": decision.recommended_option,
            "status": decision.status,
            "created_at": decision.created_at,
            "answered_at": decision.answered_at,
            "answer_json": dict(decision.answer_json or {}) if decision.answer_json else None,
            "presentation": presentation,
            "presentation_json": presentation,
        }

    def _sync_batch_pending_decision(self, db: Session, batch: SubagentBatch, *, approval_required: bool) -> PendingDecision | None:
        record = self._pending_decision_for_batch(db, batch.id)
        if not approval_required:
            if record is not None and record.status == "pending":
                record.status = "cancelled"
                record.answered_at = utc_now()
                db.flush()
            return None
        options = [
            {"id": "approve_burst", "label": "Approve burst", "description": "Use the proposed burst as-is."},
            {"id": "use_fewer_subagents", "label": "Use fewer subagents", "description": "Trim the burst to the approval-free threshold."},
            {"id": "skip_burst", "label": "Skip burst", "description": "Do not use a subagent burst for this task."},
            {"id": "manager_decides", "label": "Let Manager decide", "description": "Let Mission Control choose the safest burst shape."},
        ]
        if record is None:
            record = PendingDecision(
                project_id=batch.project_id,
                orchestration_id=batch.orchestration_id,
                decision_type="subagent_burst_approval",
                title="Mission Control recommends a Codex subagent burst",
                message=batch.reason,
                risk_level=batch.risk_level,
                options_json=options,
                recommended_option="approve_burst",
                source_kind="subagent_batch",
                source_id=batch.id,
            )
            db.add(record)
        record.project_id = batch.project_id
        record.orchestration_id = batch.orchestration_id
        record.decision_type = "subagent_burst_approval"
        record.title = "Mission Control recommends a Codex subagent burst"
        record.message = batch.reason
        record.risk_level = batch.risk_level
        record.options_json = options
        record.recommended_option = "approve_burst"
        record.status = "pending"
        record.answered_at = None
        record.answer_json = None
        record.presentation_json = {
            "card_type": "subagent_burst_approval",
            "purpose": batch.purpose,
            "subagent_count": len(batch.specs),
            "estimated_intensity": batch.estimated_intensity,
            "reason": batch.reason,
            "subagents": [spec.display_name for spec in batch.specs],
            "spawn_method": batch.spawn_method,
            "read_only_default": True,
            "commands_allowed": False,
            "options": options,
        }
        db.flush()
        return record

    def recommend_burst(self, db: Session, *, project: Project, payload: dict[str, Any], orchestration_id: int | None = None) -> dict[str, Any]:
        policy = self.ensure_policy(db)
        task_type = str(payload["task_type"])
        template_name = str(payload.get("template_name") or DEFAULT_TEMPLATE_BY_TASK_TYPE.get(task_type) or "")
        template = BURST_TEMPLATES.get(template_name)
        if template is None:
            return {
                "recommended": False,
                "suggested_burst_template": None,
                "number_of_subagents": 0,
                "reason": f"No built-in burst template is available for task type `{task_type}`.",
                "risks": ["A manual burst without a template would be too loose for the current policy."],
                "pending_decision_required": False,
                "batch": None,
                "policy": self._serialize_policy(policy),
            }

        expected_parallelism = int(payload.get("expected_parallelism") or len(template["subagents"]))
        codebase_size = str(payload.get("codebase_size") or self._project_codebase_size(project))
        task_complexity = str(payload.get("task_complexity") or "medium")
        risk_level = str(payload.get("risk_level") or "low")
        recommended, reason, risks = self._should_recommend(
            task_type=task_type,
            codebase_size=codebase_size,
            task_complexity=task_complexity,
            expected_parallelism=expected_parallelism,
            risk_level=risk_level,
            bounded_scope=bool(payload.get("bounded_scope", True)),
            requires_file_edits=bool(payload.get("requires_file_edits", False)),
            requires_commands=bool(payload.get("requires_commands", False)),
            policy=policy,
        )
        if not recommended:
            return {
                "recommended": False,
                "suggested_burst_template": template_name,
                "number_of_subagents": 0,
                "reason": reason,
                "risks": risks,
                "pending_decision_required": False,
                "batch": None,
                "policy": self._serialize_policy(policy),
            }

        count = min(expected_parallelism, len(template["subagents"]), int(policy.max_subagents_per_burst))
        estimated_intensity = self._estimated_intensity(codebase_size=codebase_size, count=count, task_complexity=task_complexity)
        approval_required = count > int(policy.require_user_approval_above_count)
        batch = SubagentBatch(
            project_id=project.id,
            orchestration_id=orchestration_id,
            purpose=str(payload["purpose"]).strip(),
            task_type=task_type,
            status="proposed" if approval_required else "approved",
            spawn_method=str(payload.get("spawn_method") or policy.default_spawn_method),
            risk_level=risk_level,
            estimated_intensity=estimated_intensity,
            reason=reason,
            approved_at=None if approval_required else utc_now(),
        )
        db.add(batch)
        db.flush()
        allowed_paths = [str(item) for item in list(payload.get("allowed_paths_json") or []) if str(item).strip()]
        forbidden_paths = [str(item) for item in list(payload.get("forbidden_paths_json") or []) if str(item).strip()]
        timeout_cap = min(int(policy.max_runtime_seconds), 600)
        for template_spec in list(template["subagents"])[:count]:
            spec = SubagentSpec(
                batch_id=batch.id,
                name=template_spec.name,
                display_name=template_spec.display_name,
                custom_agent_name=template_spec.custom_agent_name,
                mission=template_spec.mission,
                sandbox_mode="read-only",
                allowed_paths_json=allowed_paths,
                forbidden_paths_json=forbidden_paths,
                expected_output=template_spec.expected_output,
                timeout_seconds=min(template_spec.default_timeout_seconds, timeout_cap),
                status=batch.status,
            )
            db.add(spec)
        db.flush()
        db.refresh(batch)
        self._sync_batch_pending_decision(db, batch, approval_required=approval_required)
        service.events.publish(
            db,
            project.id,
            "subagent_burst_recommended",
            {
                "project_id": project.id,
                "batch_id": batch.id,
                "task_type": task_type,
                "template_name": template_name,
                "subagent_count": count,
                "approval_required": approval_required,
            },
        )
        return {
            "recommended": True,
            "suggested_burst_template": template_name,
            "number_of_subagents": count,
            "reason": reason,
            "risks": risks,
            "pending_decision_required": approval_required,
            "batch": self._serialize_batch(db, batch),
            "policy": self._serialize_policy(policy),
        }

    def list_batches(self, db: Session, project: Project) -> list[dict[str, Any]]:
        batches = list(
            db.scalars(
                select(SubagentBatch)
                .where(SubagentBatch.project_id == project.id)
                .order_by(SubagentBatch.created_at.desc(), SubagentBatch.id.desc())
            )
        )
        return [self._serialize_batch(db, batch) for batch in batches]

    def get_batch(self, db: Session, batch_id: int) -> SubagentBatch:
        batch = db.get(SubagentBatch, batch_id)
        if batch is None:
            raise ValueError("Subagent batch not found")
        return batch

    def serialize_batch(self, db: Session, batch: SubagentBatch) -> dict[str, Any]:
        return self._serialize_batch(db, batch)

    def resolve_batch_decision(self, db: Session, batch: SubagentBatch, *, option_id: str, selected_text: str) -> SubagentBatch:
        policy = self.ensure_policy(db)
        specs = list(batch.specs)
        if option_id == "approve_burst":
            batch.status = "approved"
            batch.approved_at = utc_now()
            for spec in specs:
                if spec.status == "proposed":
                    spec.status = "approved"
        elif option_id == "use_fewer_subagents":
            keep = int(policy.require_user_approval_above_count)
            batch.status = "approved"
            batch.approved_at = utc_now()
            for index, spec in enumerate(specs):
                spec.status = "approved" if index < keep else "cancelled"
            batch.summary = f"User requested a smaller burst. Trimmed to {keep} subagents."
        elif option_id == "skip_burst":
            batch.status = "cancelled"
            batch.completed_at = utc_now()
            batch.summary = "User skipped the subagent burst."
            for spec in specs:
                if spec.status not in {"completed", "failed"}:
                    spec.status = "cancelled"
        elif option_id == "manager_decides":
            batch.status = "approved"
            batch.approved_at = utc_now()
            batch.summary = "User allowed Mission Control Manager to choose the burst shape."
            for spec in specs:
                if spec.status == "proposed":
                    spec.status = "approved"
        else:
            raise ValueError("Unsupported subagent batch decision option.")
        service.events.publish(
            db,
            batch.project_id,
            "subagent_burst_decided",
            {"batch_id": batch.id, "option_id": option_id, "selected_text": selected_text},
        )
        db.flush()
        return batch

    def ingest_results(self, db: Session, batch: SubagentBatch, payload: dict[str, Any]) -> SubagentBatch:
        results = list(payload.get("results") or [])
        if not results:
            raise ValueError("At least one subagent result is required.")
        spec_lookup = {
            spec.name: spec
            for spec in batch.specs
        }
        spec_lookup.update({spec.display_name: spec for spec in batch.specs})
        for spec in batch.specs:
            if spec.custom_agent_name:
                spec_lookup[spec.custom_agent_name] = spec
        if batch.started_at is None:
            batch.started_at = utc_now()
        if batch.status in {"approved", "proposed"}:
            batch.status = "running"
        for result in results:
            key = str(result.get("subagent_name") or "").strip()
            spec = spec_lookup.get(key)
            if spec is None:
                raise ValueError(f"Unknown subagent result target: {key}")
            spec.result_summary = str(result.get("summary") or "").strip()
            spec.evidence_json = [str(item) for item in list(result.get("evidence") or []) if str(item).strip()]
            spec.risks_found_json = [str(item) for item in list(result.get("risks_found") or []) if str(item).strip()]
            spec.recommendations_json = [str(item) for item in list(result.get("recommendations") or []) if str(item).strip()]
            spec.confidence = str(result.get("confidence") or "medium")
            spec.status = "completed"
            spec.completed_at = utc_now()
        active_specs = [spec for spec in batch.specs if spec.status != "cancelled"]
        if active_specs and all(spec.status == "completed" for spec in active_specs):
            batch.status = "completed"
            batch.completed_at = utc_now()
            batch.summary = " | ".join(
                f"{spec.display_name}: {spec.result_summary}" for spec in active_specs if spec.result_summary
            )[:2000]
        db.flush()
        service.events.publish(
            db,
            batch.project_id,
            "subagent_burst_results_ingested",
            {"batch_id": batch.id, "result_count": len(results), "batch_status": batch.status},
        )
        return batch

    def generate_custom_agents(self, db: Session, project: Project, *, overwrite_existing: bool = False, template_names: list[str] | None = None) -> dict[str, Any]:
        agents_dir = Path(project.workspace_path) / ".codex" / "agents"
        agents_dir.mkdir(parents=True, exist_ok=True)
        requested = template_names or list(CUSTOM_AGENT_LIBRARY.keys())
        generated_files: list[str] = []
        skipped_existing_files: list[str] = []
        backup_files: list[str] = []
        for name in requested:
            template = CUSTOM_AGENT_LIBRARY.get(name)
            if template is None:
                continue
            file_path = agents_dir / f"{name}.toml"
            if file_path.exists() and not overwrite_existing:
                skipped_existing_files.append(file_path.as_posix())
                continue
            if file_path.exists() and overwrite_existing:
                backup_path = file_path.with_suffix(".toml.bak")
                backup_path.write_text(file_path.read_text(encoding="utf-8"), encoding="utf-8")
                backup_files.append(backup_path.as_posix())
            file_path.write_text(self._agent_toml(template), encoding="utf-8")
            generated_files.append(file_path.as_posix())
        service.events.publish(
            db,
            project.id,
            "custom_codex_agents_generated",
            {
                "project_id": project.id,
                "generated_count": len(generated_files),
                "skipped_existing_count": len(skipped_existing_files),
            },
        )
        return {
            "agents_dir": agents_dir.as_posix(),
            "generated_files": generated_files,
            "skipped_existing_files": skipped_existing_files,
            "backup_files": backup_files,
            "generated_count": len(generated_files),
        }

    def _agent_toml(self, template: BurstSpecTemplate) -> str:
        return "\n".join(
            [
                f'name = "{template.custom_agent_name or template.name}"',
                f'description = "{template.display_name} for Mission Control read-only burst work."',
                'sandbox_mode = "read-only"',
                "allow_file_edits = false",
                "allow_commands = false",
                "allow_recursive_delegation = false",
                "",
                "[developer_instructions]",
                'purpose = "Narrow read-only Mission Control helper."',
                f'mission = "{template.mission}"',
                'expected_report_format = "summary, evidence, risks, recommendations, confidence"',
                'extra = "Do not edit files. Do not run commands. Do not spawn more agents. Cite files when possible."',
                "",
                "[limits]",
                "max_depth = 1",
                "read_only_default = true",
            ]
        )


subagent_planner_service = SubagentPlannerService()
