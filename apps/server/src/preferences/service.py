from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import Project, UserPreference


class PreferenceService:
    @staticmethod
    def _is_active(record: UserPreference) -> bool:
        return record.value_json is not None

    def list_preferences(self, db: Session, *, project_id: int | None = None) -> list[UserPreference]:
        query = select(UserPreference)
        if project_id is None:
            query = query.where(UserPreference.scope == "global")
        else:
            query = query.where(UserPreference.project_id == project_id)
        return list(db.scalars(query.order_by(UserPreference.key.asc(), UserPreference.id.asc())))

    def get_effective_preferences(self, db: Session, project: Project | None = None) -> list[UserPreference]:
        global_items = list(
            db.scalars(
                select(UserPreference)
                .where(UserPreference.scope == "global")
                .order_by(UserPreference.key.asc(), UserPreference.updated_at.asc())
            )
        )
        if project is None:
            return [item for item in global_items if self._is_active(item)]
        project_items = list(
            db.scalars(
                select(UserPreference)
                .where(UserPreference.scope == "project", UserPreference.project_id == project.id)
                .order_by(UserPreference.key.asc(), UserPreference.updated_at.asc())
            )
        )
        merged: dict[str, UserPreference] = {item.key: item for item in global_items}
        for item in project_items:
            merged[item.key] = item
        return list(sorted((item for item in merged.values() if self._is_active(item)), key=lambda item: item.key))

    def upsert_preference(
        self,
        db: Session,
        *,
        key: str,
        value_json: Any,
        source: str,
        editable: bool,
        project_id: int | None = None,
    ) -> UserPreference:
        scope = "project" if project_id is not None else "global"
        query = select(UserPreference).where(UserPreference.key == key, UserPreference.scope == scope)
        if project_id is None:
            query = query.where(UserPreference.project_id.is_(None))
        else:
            query = query.where(UserPreference.project_id == project_id)
        record = db.scalar(query.order_by(UserPreference.id.asc()))
        if record is None:
            record = UserPreference(key=key, scope=scope, project_id=project_id)
            db.add(record)
        record.value_json = value_json
        record.source = source
        record.editable = editable
        db.flush()
        return record

    def preference_summary(self, db: Session, project: Project | None = None) -> dict[str, Any]:
        records = self.get_effective_preferences(db, project)
        return {
            "items": [
                {
                    "id": item.id,
                    "key": item.key,
                    "value_json": item.value_json,
                    "source": item.source,
                    "scope": item.scope,
                    "project_id": item.project_id,
                    "editable": item.editable,
                }
                for item in records
            ],
        }


preference_service = PreferenceService()
