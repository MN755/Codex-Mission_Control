from __future__ import annotations

import json
import os
from collections import Counter
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from models import (
    AgentInstructionsStatus,
    CodebaseMap,
    CodebaseUnderstanding,
    ImportedCodebaseSafety,
    InterviewQuestion,
    InterviewSession,
    Project,
    ProjectUnderstanding,
    utc_now,
)
from project_settings import get_or_create_project_settings
from security.path_validation import PathValidationError, resolve_local_path, resolve_relative_to_root


IGNORED_DIR_NAMES = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "dist",
    "build",
    "target",
    ".next",
    ".turbo",
    "coverage",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
}
TEXT_FILE_EXTENSIONS = {
    ".py",
    ".pyi",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".json",
    ".md",
    ".txt",
    ".toml",
    ".yaml",
    ".yml",
    ".ini",
    ".cfg",
    ".conf",
    ".env.example",
    ".sql",
    ".go",
    ".rs",
    ".java",
    ".cs",
    ".rb",
    ".php",
    ".c",
    ".h",
    ".cpp",
    ".hpp",
    ".swift",
    ".kt",
    ".sh",
    ".ps1",
    ".bat",
    ".cmd",
}
ENTRY_POINT_CANDIDATES = [
    "main.py",
    "app.py",
    "manage.py",
    "server.py",
    "src/main.ts",
    "src/main.tsx",
    "src/index.ts",
    "src/index.tsx",
    "src/App.tsx",
    "src/app.ts",
    "cmd/main.go",
]
CONFIG_NAMES = {
    "package.json",
    "pyproject.toml",
    "requirements.txt",
    "pnpm-workspace.yaml",
    "turbo.json",
    "vite.config.ts",
    "vite.config.js",
    "vite.config.mjs",
    "tsconfig.json",
    "dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "vercel.json",
    "netlify.toml",
    "fly.toml",
    "render.yaml",
    "render.yml",
    ".editorconfig",
    ".eslintrc",
    ".eslintrc.json",
    ".prettierrc",
    "mypy.ini",
    "tox.ini",
    "cargo.toml",
    "go.mod",
}
SECRET_LIKE_NAMES = (
    ".env",
    "secret",
    "secrets",
    "credentials",
    ".pem",
    ".key",
    "id_rsa",
    "id_dsa",
    ".p12",
)
PROJECT_IMPORT_WIDGETS = [
    "Codebase Map",
    "Codebase Understanding",
    "Imported Codebase Safety",
    "AGENTS.md Status",
    "Scan Coverage",
]


class ImportedCodebaseService:
    def _project_root(self, project: Project) -> Path:
        raw_path = project.source_path or project.workspace_path
        try:
            return resolve_local_path(raw_path, must_exist=True, must_be_dir=True)
        except PathValidationError as exc:
            raise ValueError(str(exc)) from exc

    def configure_imported_project(self, db: Session, project: Project, *, folder_path: str, import_mode: str) -> None:
        try:
            source_path = str(resolve_local_path(folder_path, must_exist=True, must_be_dir=True))
        except PathValidationError as exc:
            raise ValueError(str(exc)) from exc
        project.source_type = "existing_folder"
        project.source_path = source_path
        project.import_mode = import_mode
        project.imported_at = utc_now()
        project.scan_status = "not_started"
        project.write_permission_status = "read_only"
        project.status = "import_scanning"
        project.idea = f"Imported existing codebase from {source_path}. Understand it before proposing edits."
        project.latest_activity = f"Imported existing codebase from {Path(source_path).name}."
        settings = get_or_create_project_settings(db, project)
        settings.sandbox_mode = "read-only"
        settings.approval_policy = "untrusted"
        settings.workspace_widgets_json = list(PROJECT_IMPORT_WIDGETS)
        self.ensure_safety(db, project)
        db.flush()

    def ensure_safety(self, db: Session, project: Project, *, create_if_missing: bool = True) -> ImportedCodebaseSafety | None:
        safety = project.imported_codebase_safety
        if safety is None:
            if not create_if_missing:
                return None
            safety = ImportedCodebaseSafety(project_id=project.id)
            db.add(safety)
            db.flush()
            project.imported_codebase_safety = safety
        safety.write_permission_status = project.write_permission_status or safety.write_permission_status
        return safety

    def _ensure_codebase_map(self, db: Session, project: Project) -> CodebaseMap:
        record = project.codebase_map
        if record is None:
            record = CodebaseMap(project_id=project.id, source_path=project.source_path or project.workspace_path)
            db.add(record)
            db.flush()
            project.codebase_map = record
        return record

    def _ensure_codebase_understanding(self, db: Session, project: Project) -> CodebaseUnderstanding:
        record = project.codebase_understanding
        if record is None:
            record = CodebaseUnderstanding(project_id=project.id)
            db.add(record)
            db.flush()
            project.codebase_understanding = record
        return record

    def _ensure_agents_status(self, db: Session, project: Project) -> AgentInstructionsStatus:
        record = project.agents_md_status
        if record is None:
            record = AgentInstructionsStatus(project_id=project.id)
            db.add(record)
            db.flush()
            project.agents_md_status = record
        return record

    def _ensure_project_understanding(self, db: Session, project: Project) -> ProjectUnderstanding:
        understanding = project.understanding
        if understanding is None:
            understanding = ProjectUnderstanding(project_id=project.id)
            db.add(understanding)
            db.flush()
            project.understanding = understanding
        return understanding

    def initial_scan(self, db: Session, project: Project) -> tuple[CodebaseMap, CodebaseUnderstanding, AgentInstructionsStatus, ImportedCodebaseSafety]:
        root = self._project_root(project)
        shallow_payload = self._build_scan_payload(root, depth="shallow")
        final_depth = "standard" if shallow_payload["codebase_size"] in {"small", "medium"} else "shallow"
        payload = shallow_payload if final_depth == "shallow" else self._build_scan_payload(root, depth="standard")
        return self._apply_scan_results(db, project, payload)

    def scan_codebase(self, db: Session, project: Project, *, depth: str = "standard") -> tuple[CodebaseMap, CodebaseUnderstanding, AgentInstructionsStatus, ImportedCodebaseSafety]:
        payload = self._build_scan_payload(self._project_root(project), depth=depth)
        return self._apply_scan_results(db, project, payload)

    def targeted_scan(
        self,
        db: Session,
        project: Project,
        *,
        target_paths: list[str] | None = None,
        request_text: str | None = None,
        scan_reason: str | None = None,
    ) -> tuple[CodebaseMap, CodebaseUnderstanding, AgentInstructionsStatus, ImportedCodebaseSafety]:
        root = self._project_root(project)
        payload = self._build_scan_payload(root, depth="targeted", target_paths=target_paths)
        if request_text:
            payload["risk_flags_json"] = sorted(set(payload["risk_flags_json"] + [f"Targeted scan requested for: {request_text.strip()}"]))
        if scan_reason:
            payload["risk_flags_json"] = sorted(set(payload["risk_flags_json"] + [f"Targeted scan reason: {scan_reason.strip()}"]))
        return self._apply_scan_results(db, project, payload, merge=True)

    def _apply_scan_results(
        self,
        db: Session,
        project: Project,
        payload: dict[str, Any],
        *,
        merge: bool = False,
    ) -> tuple[CodebaseMap, CodebaseUnderstanding, AgentInstructionsStatus, ImportedCodebaseSafety]:
        project.scan_status = "in_progress"
        map_record = self._ensure_codebase_map(db, project)
        if merge:
            payload = self._merge_map_payload(map_record, payload)
        self._populate_map_record(map_record, payload)
        understanding_record = self._ensure_codebase_understanding(db, project)
        understanding_payload = self._build_understanding_payload(project, payload)
        self._populate_understanding_record(understanding_record, understanding_payload)
        agents_status = self._ensure_agents_status(db, project)
        self._populate_agents_status(agents_status, payload["agents_md"])
        self._sync_project_understanding(db, project, payload, understanding_payload)
        safety = self.ensure_safety(db, project)
        safety.read_only_scan_completed = True
        safety.write_permission_status = project.write_permission_status = "read_only" if project.source_type == "existing_folder" else project.write_permission_status
        project.scan_status = "completed"
        project.last_indexed_at = utc_now()
        project.status = "import_review"
        db.flush()
        return map_record, understanding_record, agents_status, safety

    def _merge_map_payload(self, existing: CodebaseMap, incoming: dict[str, Any]) -> dict[str, Any]:
        merged = dict(incoming)
        for field in [
            "languages_json",
            "frameworks_json",
            "package_managers_json",
            "build_tools_json",
            "test_frameworks_json",
            "entry_points_json",
            "build_commands_json",
            "test_commands_json",
            "important_folders_json",
            "docs_json",
            "config_files_json",
            "ci_config_json",
            "deployment_config_json",
            "risk_flags_json",
            "indexed_areas_json",
        ]:
            merged[field] = sorted({*list(getattr(existing, field) or []), *list(incoming.get(field, []) or [])})
        merged["agent_instructions_json"] = list(existing.agent_instructions_json or []) or list(incoming.get("agent_instructions_json", []) or [])
        merged["unindexed_areas_json"] = list(incoming.get("unindexed_areas_json", []) or [])
        return merged

    def _populate_map_record(self, record: CodebaseMap, payload: dict[str, Any]) -> None:
        record.source_path = payload["source_path"]
        record.languages_json = payload["languages_json"]
        record.frameworks_json = payload["frameworks_json"]
        record.package_managers_json = payload["package_managers_json"]
        record.build_tools_json = payload["build_tools_json"]
        record.test_frameworks_json = payload["test_frameworks_json"]
        record.entry_points_json = payload["entry_points_json"]
        record.build_commands_json = payload["build_commands_json"]
        record.test_commands_json = payload["test_commands_json"]
        record.important_folders_json = payload["important_folders_json"]
        record.docs_json = payload["docs_json"]
        record.agent_instructions_json = payload["agent_instructions_json"]
        record.config_files_json = payload["config_files_json"]
        record.ci_config_json = payload["ci_config_json"]
        record.deployment_config_json = payload["deployment_config_json"]
        record.git_status_json = payload["git_status_json"]
        record.risk_flags_json = payload["risk_flags_json"]
        record.scan_depth = payload["scan_depth"]
        record.codebase_size = payload["codebase_size"]
        record.recommended_scan_strategy = payload["recommended_scan_strategy"]
        record.indexed_areas_json = payload["indexed_areas_json"]
        record.unindexed_areas_json = payload["unindexed_areas_json"]
        record.updated_at = utc_now()

    def _populate_understanding_record(self, record: CodebaseUnderstanding, payload: dict[str, Any]) -> None:
        record.summary = payload["summary"]
        record.architecture_summary = payload["architecture_summary"]
        record.detected_stack_json = payload["detected_stack_json"]
        record.likely_run_instructions_json = payload["likely_run_instructions_json"]
        record.likely_test_instructions_json = payload["likely_test_instructions_json"]
        record.risk_summary = payload["risk_summary"]
        record.missing_context_json = payload["missing_context_json"]
        record.suggested_next_steps_json = payload["suggested_next_steps_json"]
        record.recommended_interview_mode = payload["recommended_interview_mode"]
        record.confidence_by_area_json = payload["confidence_by_area_json"]
        record.generation_mode = payload["generation_mode"]
        record.updated_at = utc_now()

    def _populate_agents_status(self, record: AgentInstructionsStatus, payload: dict[str, Any]) -> None:
        record.has_agents_md = bool(payload["has_agents_md"])
        record.agents_md_path = payload["agents_md_path"]
        record.summary = payload["summary"]
        record.recommended_action = payload["recommended_action"]
        record.updated_at = utc_now()

    def _sync_project_understanding(
        self,
        db: Session,
        project: Project,
        payload: dict[str, Any],
        understanding_payload: dict[str, Any],
    ) -> None:
        understanding = self._ensure_project_understanding(db, project)
        stack = ", ".join(understanding_payload["detected_stack_json"][:5]) or "Unknown stack"
        known_facts = {
            "codebase": [
                {"label": "Source type", "value": project.source_type},
                {"label": "Source path", "value": project.source_path or project.workspace_path},
                {"label": "Detected stack", "value": stack},
                {"label": "Scan depth", "value": payload["scan_depth"]},
                {"label": "Codebase size", "value": payload["codebase_size"]},
            ]
        }
        if payload["entry_points_json"]:
            known_facts["entry_points"] = [{"label": entry, "value": entry} for entry in payload["entry_points_json"][:6]]
        understanding.summary = understanding_payload["summary"]
        understanding.known_facts_json = known_facts
        understanding.unknowns_json = {"import": list(understanding_payload["missing_context_json"])}
        understanding.assumptions_json = []
        understanding.constraints_json = [
            "Initial imported-codebase scan is read-only.",
            "Do not read .env contents or expose secrets.",
            "Command approval is still required before install/build/test flows.",
        ]
        understanding.confidence_by_category_json = understanding_payload["confidence_by_area_json"]
        understanding.updated_at = utc_now()
        db.flush()

    def _classify_codebase_size(self, *, file_count: int, total_size: int, text_file_count: int) -> str:
        if file_count >= 20000 or total_size >= 500 * 1024 * 1024 or text_file_count >= 12000:
            return "huge"
        if file_count >= 5000 or total_size >= 100 * 1024 * 1024 or text_file_count >= 3000:
            return "large"
        if file_count >= 1000 or total_size >= 20 * 1024 * 1024 or text_file_count >= 500:
            return "medium"
        return "small"

    def _build_scan_payload(self, root: Path, *, depth: str, target_paths: list[str] | None = None) -> dict[str, Any]:
        metadata = self._collect_metadata(root)
        codebase_size = self._classify_codebase_size(
            file_count=metadata["file_count"],
            total_size=metadata["total_size"],
            text_file_count=metadata["text_file_count"],
        )
        target_roots = self._resolve_target_roots(root, target_paths)
        indexed_top_level = self._indexed_areas(metadata["top_level_dirs"], codebase_size, depth, target_roots)
        unindexed = [item for item in metadata["top_level_dirs"] if item not in indexed_top_level]
        languages = self._detect_languages(metadata["file_paths"])
        package_analysis = self._analyze_package_files(root, metadata["relative_lookup"])
        docs = self._detect_docs(metadata["file_paths"], root=root)
        agents_md = self._detect_agents_md(root, metadata["relative_lookup"])
        config_files = self._detect_config_files(metadata["file_paths"], root=root)
        ci_config = self._detect_ci_config(metadata["file_paths"], root=root)
        deployment_config = self._detect_deployment_config(metadata["file_paths"], root=root)
        entry_points = self._detect_entry_points(root, metadata["relative_lookup"])
        important_folders = self._important_folders(metadata["top_level_dirs"], metadata["relative_lookup"])
        git_status = self._detect_git_status(root)
        risk_flags = self._risk_flags(
            metadata=metadata,
            package_analysis=package_analysis,
            agents_md=agents_md,
            codebase_size=codebase_size,
            depth=depth,
            root=root,
        )
        recommended_strategy = "progressive_targeted" if codebase_size in {"large", "huge"} else "standard_complete"
        scan_depth = depth
        if depth == "standard" and codebase_size in {"large", "huge"}:
            scan_depth = "shallow"
        return {
            "project_id": 0,
            "source_path": str(root),
            "languages_json": languages,
            "frameworks_json": package_analysis["frameworks"],
            "package_managers_json": package_analysis["package_managers"],
            "build_tools_json": package_analysis["build_tools"],
            "test_frameworks_json": package_analysis["test_frameworks"],
            "entry_points_json": entry_points,
            "build_commands_json": package_analysis["build_commands"],
            "test_commands_json": package_analysis["test_commands"],
            "important_folders_json": important_folders,
            "docs_json": docs,
            "agent_instructions_json": agents_md["entries"],
            "agents_md": agents_md,
            "config_files_json": config_files,
            "ci_config_json": ci_config,
            "deployment_config_json": deployment_config,
            "git_status_json": git_status,
            "risk_flags_json": risk_flags,
            "scan_depth": scan_depth,
            "codebase_size": codebase_size,
            "recommended_scan_strategy": recommended_strategy,
            "indexed_areas_json": indexed_top_level,
            "unindexed_areas_json": unindexed,
            "file_count": metadata["file_count"],
            "directory_count": metadata["directory_count"],
            "text_file_count": metadata["text_file_count"],
            "total_size": metadata["total_size"],
        }

    def _build_understanding_payload(self, project: Project, payload: dict[str, Any]) -> dict[str, Any]:
        stack = payload["frameworks_json"] + [language for language in payload["languages_json"] if language not in payload["frameworks_json"]]
        summary_bits = []
        if payload["frameworks_json"]:
            summary_bits.append(", ".join(payload["frameworks_json"][:4]))
        elif payload["languages_json"]:
            summary_bits.append(", ".join(payload["languages_json"][:4]))
        else:
            summary_bits.append("a mixed local codebase")
        summary = f"This appears to be {summary_bits[0]} in {Path(payload['source_path']).name}."
        architecture_parts = []
        if payload["important_folders_json"]:
            architecture_parts.append(f"Key areas: {', '.join(payload['important_folders_json'][:8])}.")
        if payload["entry_points_json"]:
            architecture_parts.append(f"Likely entry points: {', '.join(payload['entry_points_json'][:5])}.")
        if payload["docs_json"]:
            architecture_parts.append(f"Docs found: {', '.join(payload['docs_json'][:5])}.")
        architecture_summary = " ".join(architecture_parts) or "The repo structure is only partially mapped so far."
        missing_context: list[str] = []
        if not payload["build_commands_json"]:
            missing_context.append("No reliable build command was detected.")
        if not payload["test_commands_json"]:
            missing_context.append("No reliable test command was detected.")
        if not payload["docs_json"]:
            missing_context.append("Documentation is thin or missing.")
        if payload["scan_depth"] == "shallow" and payload["codebase_size"] in {"large", "huge"}:
            missing_context.append("This codebase is large. Progressive understanding is active, so only high-signal areas are indexed now.")
        if payload["git_status_json"].get("is_git_repo") and payload["git_status_json"].get("dirty_working_tree") == "unknown_without_command":
            missing_context.append("Working tree cleanliness is unknown because the initial import scan does not run git commands.")
        if not payload["agent_instructions_json"]:
            missing_context.append("No AGENTS.md instructions were detected.")
        suggested_next_steps = [
            "Review the Codebase Understanding report before asking for edits.",
            "Choose skip, quick clarification, full interview, or let the Manager decide.",
        ]
        if payload["scan_depth"] == "shallow" and payload["codebase_size"] in {"large", "huge"}:
            suggested_next_steps.append("Use targeted scan on the subsystem you want to change first.")
        if not payload["agent_instructions_json"]:
            suggested_next_steps.append("Consider creating an AGENTS.md file before handing the repo to editing agents.")
        if project.write_permission_status == "read_only":
            suggested_next_steps.append("Grant write permission only when you are ready for actual edits.")
        confidence = {
            "architecture": 0.84 if payload["important_folders_json"] else 0.42,
            "run_commands": 0.92 if payload["build_commands_json"] else 0.28,
            "test_commands": 0.9 if payload["test_commands_json"] else 0.24,
            "framework_detection": 0.95 if payload["frameworks_json"] else 0.35,
            "safety": 0.95,
            "docs": 0.88 if payload["docs_json"] else 0.2,
            "entry_points": 0.9 if payload["entry_points_json"] else 0.3,
        }
        if payload["codebase_size"] == "huge":
            confidence["architecture"] = min(confidence["architecture"], 0.62)
            confidence["entry_points"] = min(confidence["entry_points"], 0.58)
        avg_confidence = sum(confidence.values()) / max(len(confidence), 1)
        if avg_confidence >= 0.78 and len(missing_context) <= 2:
            recommended_interview_mode = "skip"
        elif avg_confidence <= 0.45 or len(missing_context) >= 5:
            recommended_interview_mode = "full"
        elif payload["codebase_size"] in {"large", "huge"}:
            recommended_interview_mode = "manager_decides"
        else:
            recommended_interview_mode = "quick"
        risk_parts = list(payload["risk_flags_json"][:6])
        if not risk_parts:
            risk_parts.append("No immediate high-risk signals were detected during the read-only scan.")
        return {
            "project_id": project.id,
            "summary": summary,
            "architecture_summary": architecture_summary,
            "detected_stack_json": stack[:10],
            "likely_run_instructions_json": payload["build_commands_json"][:5],
            "likely_test_instructions_json": payload["test_commands_json"][:5],
            "risk_summary": " ".join(risk_parts),
            "missing_context_json": missing_context,
            "suggested_next_steps_json": suggested_next_steps,
            "recommended_interview_mode": recommended_interview_mode,
            "confidence_by_area_json": confidence,
            "generation_mode": "deterministic_scanner",
        }

    def get_codebase_map(self, db: Session, project: Project) -> CodebaseMap:
        return self._ensure_codebase_map(db, project)

    def get_codebase_understanding(self, db: Session, project: Project) -> CodebaseUnderstanding:
        return self._ensure_codebase_understanding(db, project)

    def get_agents_status(self, db: Session, project: Project) -> AgentInstructionsStatus:
        return self._ensure_agents_status(db, project)

    def choose_interview_mode(self, db: Session, project: Project, *, choice: str) -> tuple[str, list[InterviewQuestion], str]:
        understanding = self._ensure_codebase_understanding(db, project)
        effective_choice = choice
        if choice == "manager_decides":
            effective_choice = understanding.recommended_interview_mode
        if effective_choice == "skip":
            project.status = "draft"
            db.flush()
            return f"/projects/{project.id}", [], "The current codebase understanding is strong enough to skip the interview for now."
        questions_payload = self._build_import_questions(project, understanding, full=effective_choice == "full")
        session = InterviewSession(
            project_id=project.id,
            question_count=len(questions_payload),
            question_budget=len(questions_payload),
            questions_asked=len(questions_payload),
            current_index=0,
            status="in_progress",
            manager_mode=project.manager_mode,
        )
        db.add(session)
        db.flush()
        records: list[InterviewQuestion] = []
        for index, payload in enumerate(questions_payload):
            question = InterviewQuestion(
                session_id=session.id,
                project_id=project.id,
                index=index,
                question=payload["question"],
                why=payload["why"],
                category=payload["category"],
                impact=payload["impact"],
                options_json=payload["options"],
                allow_custom_answer=True,
                affects_json=payload["affects"],
                question_source="fallback_generated",
                status="pending",
            )
            db.add(question)
            records.append(question)
        project.status = "interview_in_progress"
        db.flush()
        note = (
            "Quick clarification keeps the question set narrow and repo-specific."
            if effective_choice == "quick"
            else "Full interview starts from the scan results instead of asking the usual generic intake questions."
        )
        return f"/projects/{project.id}/interview", records, note

    def _build_import_questions(self, project: Project, understanding: CodebaseUnderstanding, *, full: bool) -> list[dict[str, Any]]:
        questions = [
            {
                "question": "Should Mission Control preserve the existing architecture unless you explicitly approve larger structural changes?",
                "why": "Imported repos need guardrails before anyone starts 'improving' them into a different product.",
                "category": "core features",
                "impact": "high",
                "affects": ["architecture", "refactor"],
                "options": [
                    {"id": "preserve", "label": "Preserve architecture", "description": "Prefer local fixes and incremental changes."},
                    {"id": "evolve", "label": "Allow bigger changes", "description": "Permit meaningful architectural updates when justified."},
                    {"id": "recommend", "label": "Recommend one", "description": "Let the Manager decide case by case."},
                ],
            },
            {
                "question": "Can Mission Control add dependencies if needed, or should it stay inside the current dependency set first?",
                "why": "Dependency policy changes the safe path for bug fixes, tests, and feature work immediately.",
                "category": "integrations/connectors",
                "impact": "high",
                "affects": ["dependencies", "build"],
                "options": [
                    {"id": "no_new_deps", "label": "Avoid new dependencies", "description": "Prefer existing tools and libraries first."},
                    {"id": "deps_allowed", "label": "Dependencies allowed", "description": "Allow package changes when they are justified."},
                    {"id": "recommend", "label": "Recommend one", "description": "Let the Manager decide case by case."},
                ],
            },
            {
                "question": "What should the Manager prioritize first in this imported codebase?",
                "why": "The scanner can see structure. It still cannot guess your actual priority with a straight face.",
                "category": "product goal",
                "impact": "high",
                "affects": ["planning", "execution"],
                "options": [
                    {"id": "bugfix", "label": "Bug fixes", "description": "Stabilize the current code before adding scope."},
                    {"id": "feature", "label": "Feature work", "description": "Ship the next capability first."},
                    {"id": "tests", "label": "Tests and reliability", "description": "Harden validation and confidence first."},
                    {"id": "docs", "label": "Docs and explanation", "description": "Prioritize repo understanding and documentation."},
                ],
            },
            {
                "question": "Should Mission Control recommend a snapshot or branch checkpoint before editing if the repo is under git?",
                "why": "Imported repos deserve a safety net before edits. Revolutionary insight, apparently.",
                "category": "approvals/sandboxing",
                "impact": "medium",
                "affects": ["safety", "git"],
                "options": [
                    {"id": "snapshot_yes", "label": "Recommend snapshot", "description": "Bias toward a checkpoint before edits."},
                    {"id": "snapshot_no", "label": "Skip snapshot recommendation", "description": "Do not block on git safety prep."},
                    {"id": "recommend", "label": "Recommend one", "description": "Let the Manager decide case by case."},
                ],
            },
        ]
        if not project.agents_md_status or not project.agents_md_status.has_agents_md:
            questions.append(
                {
                    "question": "Should Mission Control propose an AGENTS.md file for this repo before deeper edits?",
                    "why": "Agent instructions are more useful than hoping future sessions read your mind correctly.",
                    "category": "agent/tool behavior",
                    "impact": "medium",
                    "affects": ["docs", "agent guidance"],
                    "options": [
                        {"id": "propose_agents", "label": "Propose AGENTS.md", "description": "Generate a proposal for review before writing anything."},
                        {"id": "skip_agents", "label": "Skip for now", "description": "Do not spend time on AGENTS.md yet."},
                        {"id": "recommend", "label": "Recommend one", "description": "Let the Manager decide."},
                    ],
                }
            )
        if full:
            questions.extend(
                [
                    {
                        "question": "Can Mission Control modify package manager files, lockfiles, and build configuration when that is the smallest real fix?",
                        "why": "Package and build files are the first place 'small changes' go to become political.",
                        "category": "platform/runtime",
                        "impact": "medium",
                        "affects": ["build", "dependencies"],
                        "options": [
                            {"id": "package_no", "label": "Avoid package files", "description": "Do not touch package manager files without explicit approval."},
                            {"id": "package_yes", "label": "Allow package files", "description": "Permit package and build config changes when needed."},
                            {"id": "recommend", "label": "Recommend one", "description": "Let the Manager decide."},
                        ],
                    },
                    {
                        "question": "Should the Manager favor tests, direct fixes, docs, or refactors when there is a tradeoff?",
                        "why": "This tells the system what to sacrifice first instead of improvising values later.",
                        "category": "testing/validation",
                        "impact": "medium",
                        "affects": ["validation", "execution"],
                        "options": [
                            {"id": "favor_tests", "label": "Favor tests", "description": "Bias toward validation and regression safety."},
                            {"id": "favor_fixes", "label": "Favor direct fixes", "description": "Ship the functional change first."},
                            {"id": "favor_docs", "label": "Favor docs", "description": "Prioritize understanding and explanation first."},
                            {"id": "favor_refactor", "label": "Favor refactor", "description": "Clean structure early when it unlocks the work."},
                        ],
                    },
                ]
            )
        weakest = sorted(
            understanding.confidence_by_area_json.items(),
            key=lambda item: item[1],
        )[:2]
        for area, _score in weakest:
            if area in {"run_commands", "test_commands"}:
                questions.append(
                    {
                        "question": f"What is the safest expected way to handle {area.replace('_', ' ')} in this repo?",
                        "why": "The scanner can infer commands, but repo-specific expectations still matter before execution.",
                        "category": "testing/validation" if "test" in area else "platform/runtime",
                        "impact": "medium",
                        "affects": [area],
                        "options": [
                            {"id": "strict", "label": "Ask before running", "description": "Require explicit approval before command execution."},
                            {"id": "normal", "label": "Use likely command", "description": "Proceed with the best detected command when approved."},
                            {"id": "recommend", "label": "Recommend one", "description": "Let the Manager decide."},
                        ],
                    }
                )
        return questions[:8 if full else 5]

    def analyze_manager_request(self, db: Session, project: Project, *, message: str) -> dict[str, Any]:
        understanding = self._ensure_codebase_understanding(db, project)
        codebase_map = self._ensure_codebase_map(db, project)
        safety = self.ensure_safety(db, project)
        lowered = message.lower()
        classification = self._classify_request(lowered)
        targeted = self._suggest_targets(codebase_map, lowered)
        warnings: list[str] = []
        if codebase_map.codebase_size in {"large", "huge"} and codebase_map.scan_depth == "shallow":
            warnings.append("This codebase is still in progressive understanding mode. A targeted scan may be smarter than pretending the whole repo was deeply mapped.")
        if classification in {"bugfix", "feature", "refactor", "docs", "test", "migration", "cleanup"} and safety.write_permission_status == "read_only":
            return {
                "project_id": project.id,
                "classification": classification,
                "decision": "request_write_permission",
                "manager_note": "This looks like edit work, but imported codebases stay read-only until you explicitly allow writes.",
                "suggested_questions": [],
                "targeted_scan_targets": targeted,
                "warnings": warnings,
            }
        if classification in {"bugfix", "feature", "refactor", "migration", "cleanup"} and safety.require_snapshot_before_edits and codebase_map.git_status_json.get("is_git_repo"):
            return {
                "project_id": project.id,
                "classification": classification,
                "decision": "recommend_snapshot_first",
                "manager_note": "A snapshot or branch checkpoint is recommended before edits on imported repos under git.",
                "suggested_questions": [],
                "targeted_scan_targets": targeted,
                "warnings": warnings,
            }
        if ("test" in lowered or classification == "test") and safety.require_approval_for_test_commands:
            return {
                "project_id": project.id,
                "classification": classification,
                "decision": "request_command_approval",
                "manager_note": "Test execution still requires approval in imported safety mode.",
                "suggested_questions": [],
                "targeted_scan_targets": targeted,
                "warnings": warnings,
            }
        if ("build" in lowered or "run " in lowered) and safety.require_approval_for_build_commands:
            return {
                "project_id": project.id,
                "classification": classification,
                "decision": "request_command_approval",
                "manager_note": "Build or run commands still require approval in imported safety mode.",
                "suggested_questions": [],
                "targeted_scan_targets": targeted,
                "warnings": warnings,
            }
        if targeted and codebase_map.codebase_size in {"large", "huge"}:
            return {
                "project_id": project.id,
                "classification": classification,
                "decision": "run_targeted_scan",
                "manager_note": "The request points at a specific subsystem. Targeted scan first, then plan the work with less guessing.",
                "suggested_questions": [],
                "targeted_scan_targets": targeted,
                "warnings": warnings,
            }
        if classification == "analysis" and not understanding.missing_context_json:
            decision = "answer_directly"
            note = "The Manager already has enough scanner context to explain the repo directly."
        elif classification == "analysis":
            decision = "ask_quick_question"
            note = "The Manager can explain most of the repo now, but one or two clarifications would keep it from bullshitting the gaps."
        else:
            decision = "create_task_plan"
            note = "The next sensible step is a scoped plan based on the imported codebase context."
        suggested_questions = list(understanding.missing_context_json[:3]) if decision == "ask_quick_question" else []
        return {
            "project_id": project.id,
            "classification": classification,
            "decision": decision,
            "manager_note": note,
            "suggested_questions": suggested_questions,
            "targeted_scan_targets": targeted,
            "warnings": warnings,
        }

    def _classify_request(self, lowered: str) -> str:
        mapping = [
            ("security", ["security", "vulnerability", "secret", "auth"]),
            ("performance", ["performance", "slow", "latency", "optimize"]),
            ("migration", ["migrate", "upgrade", "port"]),
            ("docs", ["docs", "document", "readme", "explain"]),
            ("test", ["test", "failing", "pass"]),
            ("bugfix", ["bug", "fix", "broken", "error"]),
            ("feature", ["feature", "add ", "implement"]),
            ("refactor", ["refactor", "cleanup architecture", "restructure"]),
            ("cleanup", ["cleanup", "tidy", "simplify"]),
            ("analysis", ["explain", "summarize", "architecture", "what does", "how does"]),
        ]
        for label, triggers in mapping:
            if any(trigger in lowered for trigger in triggers):
                return label
        return "unknown"

    def _suggest_targets(self, codebase_map: CodebaseMap, lowered: str) -> list[str]:
        candidates = []
        for path in codebase_map.important_folders_json or []:
            folder_name = Path(path).name.lower()
            if folder_name and folder_name in lowered:
                candidates.append(path)
        if not candidates and any(word in lowered for word in ["frontend", "ui", "react"]):
            candidates.extend([path for path in codebase_map.important_folders_json if any(token in path.lower() for token in ["src", "client", "frontend", "ui"])][:2])
        if not candidates and any(word in lowered for word in ["backend", "api", "server", "database"]):
            candidates.extend([path for path in codebase_map.important_folders_json if any(token in path.lower() for token in ["server", "api", "backend", "db", "migrations"])][:2])
        return candidates[:4]

    def update_safety(self, db: Session, project: Project, payload: dict[str, Any]) -> ImportedCodebaseSafety:
        safety = self.ensure_safety(db, project)
        for field, value in payload.items():
            if value is None or not hasattr(safety, field):
                continue
            setattr(safety, field, value)
        if payload.get("write_permission_status"):
            project.write_permission_status = str(payload["write_permission_status"])
            safety.write_permission_status = str(payload["write_permission_status"])
            if project.write_permission_status != "read_only":
                project.status = "draft"
        safety.updated_at = utc_now()
        db.flush()
        return safety

    def propose_agents_md(self, db: Session, project: Project) -> dict[str, Any]:
        codebase_map = self._ensure_codebase_map(db, project)
        understanding = self._ensure_codebase_understanding(db, project)
        commands = [
            *list(codebase_map.build_commands_json or [])[:2],
            *list(codebase_map.test_commands_json or [])[:2],
        ]
        recommended_path = str(self._project_root(project) / "AGENTS.md")
        summary = "Proposal only. Nothing is written until the user approves it."
        proposal_markdown = "\n".join(
            [
                "# AGENTS.md",
                "",
                "## Project Overview",
                understanding.summary or f"Imported codebase at {project.source_path or project.workspace_path}.",
                "",
                "## Setup Commands",
                *([f"- `{command}`" for command in commands] or ["- Document setup after the first approved validation pass."]),
                "",
                "## Run Commands",
                *([f"- `{command}`" for command in codebase_map.build_commands_json[:3]] or ["- No reliable run command detected yet."]),
                "",
                "## Test Commands",
                *([f"- `{command}`" for command in codebase_map.test_commands_json[:3]] or ["- No reliable test command detected yet."]),
                "",
                "## Code Style",
                "- Preserve the existing architecture unless the user approves broader structural changes.",
                "- Avoid dependency changes, mass formatting, or package-file edits without approval.",
                "- Keep initial analysis read-only and never expose secret contents.",
                "",
                "## Architecture Notes",
                understanding.architecture_summary or "Architecture notes still need refinement.",
                "",
                "## Do-Not-Touch Areas",
                "- Secrets, `.env` files, and credential material.",
                "- Ignored build artifacts and dependency directories unless explicitly asked.",
                "",
                "## Safety Rules",
                "- Recommend a snapshot before risky edits in imported repos.",
                "- Ask for approval before build, test, install, or destructive commands.",
                "",
                "## Agent Completion Report Format",
                "- Summary of changes",
                "- Files changed",
                "- Tests/builds run",
                "- Known limitations and follow-up risks",
            ]
        )
        return {
            "project_id": project.id,
            "recommended_path": recommended_path,
            "summary": summary,
            "proposal_markdown": proposal_markdown,
        }

    def _collect_metadata(self, root: Path) -> dict[str, Any]:
        file_paths: list[Path] = []
        top_level_dirs: list[str] = []
        relative_lookup: dict[str, Path] = {}
        file_count = 0
        directory_count = 0
        text_file_count = 0
        total_size = 0
        large_files: list[tuple[str, int]] = []
        for current_root, dirnames, filenames in os.walk(root):
            current_path = Path(current_root)
            dirnames[:] = [name for name in dirnames if name not in IGNORED_DIR_NAMES]
            if current_path == root:
                top_level_dirs = sorted(dirnames)
            directory_count += len(dirnames)
            for filename in filenames:
                path = current_path / filename
                try:
                    relative = str(path.relative_to(root)).replace("\\", "/")
                    stat = path.stat()
                except OSError:
                    continue
                relative_lookup[relative] = path
                file_paths.append(path)
                file_count += 1
                total_size += stat.st_size
                if self._is_probably_text(path):
                    text_file_count += 1
                if stat.st_size >= 5 * 1024 * 1024:
                    large_files.append((relative, stat.st_size))
        large_files.sort(key=lambda item: item[1], reverse=True)
        return {
            "file_paths": file_paths,
            "relative_lookup": relative_lookup,
            "top_level_dirs": top_level_dirs,
            "file_count": file_count,
            "directory_count": directory_count,
            "text_file_count": text_file_count,
            "total_size": total_size,
            "large_files": large_files[:10],
        }

    def _is_probably_text(self, path: Path) -> bool:
        suffix = path.suffix.lower()
        if suffix in TEXT_FILE_EXTENSIONS:
            return True
        return suffix == "" and path.name.lower() in {"dockerfile", "makefile", "procfile", "readme", "agents.md"}

    def _resolve_target_roots(self, root: Path, target_paths: list[str] | None) -> list[str]:
        if not target_paths:
            return []
        resolved_root = resolve_local_path(root, must_exist=True, must_be_dir=True)
        resolved: list[str] = []
        for target in target_paths:
            try:
                candidate = resolve_relative_to_root(resolved_root, target, must_exist=True)
            except PathValidationError:
                continue
            resolved.append(str(candidate.relative_to(resolved_root)).replace("\\", "/"))
        return sorted(set(resolved))

    def _indexed_areas(self, top_level_dirs: list[str], codebase_size: str, depth: str, target_roots: list[str]) -> list[str]:
        if target_roots:
            return target_roots
        if not top_level_dirs:
            return ["."]
        if depth == "standard" and codebase_size in {"small", "medium"}:
            return top_level_dirs
        return top_level_dirs[: min(len(top_level_dirs), 6 if codebase_size == "large" else 4)]

    def _detect_languages(self, file_paths: list[Path]) -> list[str]:
        extension_map = {
            ".py": "Python",
            ".ts": "TypeScript",
            ".tsx": "TypeScript",
            ".js": "JavaScript",
            ".jsx": "JavaScript",
            ".go": "Go",
            ".rs": "Rust",
            ".java": "Java",
            ".cs": "C#",
            ".rb": "Ruby",
            ".php": "PHP",
            ".swift": "Swift",
            ".kt": "Kotlin",
            ".sql": "SQL",
        }
        extensions = Counter(path.suffix.lower() for path in file_paths)
        return sorted({language for suffix, language in extension_map.items() if extensions.get(suffix)})

    def _analyze_package_files(self, root: Path, lookup: dict[str, Path]) -> dict[str, list[str]]:
        frameworks: set[str] = set()
        package_managers: set[str] = set()
        build_tools: set[str] = set()
        test_frameworks: set[str] = set()
        build_commands: list[str] = []
        test_commands: list[str] = []
        risk_flags: list[str] = []
        package_json = lookup.get("package.json")
        package_manager_prefix = "npm"
        if package_json and package_json.exists():
            package_managers.add("npm")
            if lookup.get("pnpm-lock.yaml"):
                package_managers.add("pnpm")
                package_manager_prefix = "pnpm"
            if lookup.get("yarn.lock"):
                package_managers.add("yarn")
                package_manager_prefix = "yarn"
            if lookup.get("bun.lockb") or lookup.get("bun.lock"):
                package_managers.add("bun")
                package_manager_prefix = "bun"
            try:
                package_data = json.loads(package_json.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                package_data = {}
            deps = {
                **dict(package_data.get("dependencies") or {}),
                **dict(package_data.get("devDependencies") or {}),
            }
            scripts = dict(package_data.get("scripts") or {})
            dependency_map = {
                "react": "React",
                "next": "Next.js",
                "vite": "Vite",
                "vue": "Vue",
                "@angular/core": "Angular",
                "svelte": "Svelte",
                "express": "Express",
                "fastify": "Fastify",
                "nestjs": "NestJS",
                "@nestjs/core": "NestJS",
                "electron": "Electron",
            }
            for dependency, framework in dependency_map.items():
                if dependency in deps:
                    frameworks.add(framework)
            if any(key in deps for key in {"vite", "webpack", "rollup", "esbuild"}):
                for key, label in {"vite": "Vite", "webpack": "Webpack", "rollup": "Rollup", "esbuild": "esbuild"}.items():
                    if key in deps:
                        build_tools.add(label)
            if "typescript" in deps:
                build_tools.add("TypeScript")
            if "vitest" in deps:
                test_frameworks.add("Vitest")
            if "jest" in deps:
                test_frameworks.add("Jest")
            if "playwright" in deps or "@playwright/test" in deps:
                test_frameworks.add("Playwright")
            if "cypress" in deps:
                test_frameworks.add("Cypress")
            if scripts.get("build"):
                build_commands.append(f"{package_manager_prefix} run build")
            if scripts.get("dev") and not build_commands:
                build_commands.append(f"{package_manager_prefix} run dev")
            if scripts.get("test"):
                test_commands.append(f"{package_manager_prefix} run test")
            risky_fragments = ["curl ", "wget ", "rm -rf", "sudo ", "powershell -enc", "invoke-webrequest", "del /f"]
            for script_name, script_value in scripts.items():
                lowered = str(script_value).lower()
                if script_name in {"preinstall", "postinstall"} or any(fragment in lowered for fragment in risky_fragments):
                    risk_flags.append(f"Risky package script detected: {script_name}")
        for filename, manager_name in [("pyproject.toml", "pip"), ("requirements.txt", "pip"), ("uv.lock", "uv"), ("poetry.lock", "poetry"), ("Pipfile", "pipenv")]:
            if lookup.get(filename):
                package_managers.add(manager_name)
        pyproject = lookup.get("pyproject.toml")
        if pyproject and pyproject.exists():
            try:
                pyproject_text = pyproject.read_text(encoding="utf-8").lower()
            except OSError:
                pyproject_text = ""
            for needle, label in {"fastapi": "FastAPI", "django": "Django", "flask": "Flask", "pytest": "Pytest", "sqlalchemy": "SQLAlchemy"}.items():
                if needle in pyproject_text:
                    if label in {"Pytest"}:
                        test_frameworks.add(label)
                    else:
                        frameworks.add(label)
            if "[tool.pytest" in pyproject_text:
                test_frameworks.add("Pytest")
            if "[tool.poetry" in pyproject_text:
                build_tools.add("Poetry")
            if "[tool.hatch" in pyproject_text:
                build_tools.add("Hatch")
        requirements = lookup.get("requirements.txt")
        if requirements and requirements.exists():
            try:
                requirements_text = requirements.read_text(encoding="utf-8").lower()
            except OSError:
                requirements_text = ""
            for needle, label in {"fastapi": "FastAPI", "django": "Django", "flask": "Flask", "pytest": "Pytest"}.items():
                if needle in requirements_text:
                    if label == "Pytest":
                        test_frameworks.add(label)
                    else:
                        frameworks.add(label)
        if lookup.get("go.mod"):
            package_managers.add("go")
            build_tools.add("Go Modules")
            if lookup.get("go.sum"):
                test_frameworks.add("go test")
        if lookup.get("Cargo.toml"):
            package_managers.add("cargo")
            build_tools.add("Cargo")
            test_frameworks.add("cargo test")
        return {
            "frameworks": sorted(frameworks),
            "package_managers": sorted(package_managers),
            "build_tools": sorted(build_tools),
            "test_frameworks": sorted(test_frameworks),
            "build_commands": build_commands[:6],
            "test_commands": test_commands[:6],
            "risk_flags": risk_flags,
        }

    def _detect_entry_points(self, root: Path, lookup: dict[str, Path]) -> list[str]:
        found = [candidate for candidate in ENTRY_POINT_CANDIDATES if candidate in lookup or (root / candidate).exists()]
        return found[:10]

    def _important_folders(self, top_level_dirs: list[str], lookup: dict[str, Path]) -> list[str]:
        preferred = []
        for name in top_level_dirs:
            lowered = name.lower()
            if lowered in {"src", "app", "apps", "server", "client", "frontend", "backend", "api", "docs", "tests", "scripts", "packages", "services"}:
                preferred.append(name)
        if not preferred:
            preferred = top_level_dirs[:8]
        if not preferred and lookup:
            preferred = sorted({Path(relative).parts[0] for relative in lookup if "/" in relative})[:8]
        return preferred[:10]

    def _detect_docs(self, file_paths: list[Path], *, root: Path) -> list[str]:
        docs = []
        for path in file_paths:
            lowered = path.name.lower()
            relative = str(path)
            if lowered.startswith("readme") or lowered == "contributing.md" or "docs" in path.parts:
                docs.append(relative.replace("\\", "/"))
        return [self._trim_relative_path(path, root=root) for path in docs[:24]]

    def _detect_agents_md(self, root: Path, lookup: dict[str, Path]) -> dict[str, Any]:
        candidates = [
            relative
            for relative in sorted(lookup)
            if Path(relative).name.lower() == "agents.md"
        ]
        entries = []
        summary = "No AGENTS.md file detected. Recommend proposing one before broad agent-driven edits."
        recommended_action = "create"
        agents_md_path = None
        if candidates:
            agents_md_path = str((root / candidates[0]).resolve())
            snippet = self._safe_read_text(lookup[candidates[0]], limit=1600)
            lines = [line.strip() for line in snippet.splitlines() if line.strip()] if snippet else []
            snippet_summary = " ".join(lines[:6])[:320] if lines else "AGENTS.md detected, but it could not be summarized cleanly."
            entries = [{"path": str((root / relative).resolve()), "summary": snippet_summary} for relative in candidates[:4]]
            summary = snippet_summary
            recommended_action = "review" if len(lines) >= 3 else "update"
        return {
            "has_agents_md": bool(candidates),
            "agents_md_path": agents_md_path,
            "entries": entries,
            "summary": summary,
            "recommended_action": recommended_action if candidates else "create",
        }

    def _detect_config_files(self, file_paths: list[Path], *, root: Path) -> list[str]:
        results = []
        for path in file_paths:
            relative = self._trim_relative_path(str(path), root=root)
            if path.name.lower() in CONFIG_NAMES or path.name.startswith(".env"):
                results.append(relative)
        return sorted(set(results))[:40]

    def _detect_ci_config(self, file_paths: list[Path], *, root: Path) -> list[str]:
        results = []
        for path in file_paths:
            relative = self._trim_relative_path(str(path), root=root)
            lowered = path.name.lower()
            if ".github" in path.parts or lowered in {"azure-pipelines.yml", "azure-pipelines.yaml", ".gitlab-ci.yml"}:
                results.append(relative)
        return sorted(set(results))[:24]

    def _detect_deployment_config(self, file_paths: list[Path], *, root: Path) -> list[str]:
        names = {"dockerfile", "docker-compose.yml", "docker-compose.yaml", "vercel.json", "fly.toml", "render.yaml", "render.yml", "netlify.toml", "procfile"}
        return sorted(
            {
                self._trim_relative_path(str(path), root=root)
                for path in file_paths
                if path.name.lower() in names
            }
        )[:24]

    def _detect_git_status(self, root: Path) -> dict[str, Any]:
        git_dir = root / ".git"
        is_git_repo = git_dir.exists()
        head_ref = None
        if git_dir.is_dir():
            head = git_dir / "HEAD"
            try:
                if head.exists():
                    content = head.read_text(encoding="utf-8").strip()
                    head_ref = content.removeprefix("ref: ").strip() if content.startswith("ref: ") else content[:40]
            except OSError:
                head_ref = None
        elif git_dir.is_file():
            is_git_repo = True
            head_ref = "gitdir indirection"
        return {
            "is_git_repo": is_git_repo,
            "head_ref": head_ref,
            "dirty_working_tree": "unknown_without_command" if is_git_repo else "not_git",
            "command_required_for_dirty_check": is_git_repo,
        }

    def _risk_flags(
        self,
        *,
        metadata: dict[str, Any],
        package_analysis: dict[str, list[str]],
        agents_md: dict[str, Any],
        codebase_size: str,
        depth: str,
        root: Path,
    ) -> list[str]:
        flags = []
        for relative, size in metadata["large_files"][:5]:
            flags.append(f"Large file detected: {relative} ({round(size / (1024 * 1024), 1)} MB)")
        for path in metadata["file_paths"]:
            lowered = path.name.lower()
            if any(fragment in lowered for fragment in SECRET_LIKE_NAMES):
                flags.append(f"Secret-like filename detected: {self._trim_relative_path(str(path), root=root)}")
        flags.extend(package_analysis["risk_flags"])
        if codebase_size in {"large", "huge"} and depth == "shallow":
            flags.append("Large codebase: progressive understanding is active, so unindexed areas remain.")
        if not agents_md["has_agents_md"]:
            flags.append("AGENTS.md is missing.")
        return sorted(set(flags))[:16]

    def _safe_read_text(self, path: Path, *, limit: int = 200_000) -> str:
        try:
            if path.stat().st_size > limit:
                return ""
            return path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return ""

    def _trim_relative_path(self, value: str, *, root: Path | None = None) -> str:
        normalized = value.replace("\\", "/")
        if root is not None:
            try:
                relative = Path(normalized).resolve().relative_to(root.resolve())
            except (OSError, ValueError):
                relative = None
            if relative is not None:
                return relative.as_posix()
        if "/workspace/" in normalized:
            return normalized.split("/workspace/", 1)[1]
        return normalized


import_service = ImportedCodebaseService()
