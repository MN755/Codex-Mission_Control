from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import Project, UserPreference


class PreferenceService:
    @staticmethod
    def _normalize_key(key: str) -> str:
        normalized = key.strip()
        if not normalized:
            raise ValueError("Preference key cannot be blank")
        return normalized

    @staticmethod
    def _is_active(record: UserPreference) -> bool:
        return record.value_json is not None

    def _records_for_scope(self, db: Session, *, key: str, project_id: int | None) -> list[UserPreference]:
        normalized_key = self._normalize_key(key)
        scope = "project" if project_id is not None else "global"
        query = select(UserPreference).where(UserPreference.key == normalized_key, UserPreference.scope == scope)
        if project_id is None:
            query = query.where(UserPreference.project_id.is_(None))
        else:
            query = query.where(UserPreference.project_id == project_id)
        return list(db.scalars(query.order_by(UserPreference.updated_at.desc(), UserPreference.id.desc())))

    def list_preferences(self, db: Session, *, project_id: int | None = None) -> list[UserPreference]:
        query = select(UserPreference)
        if project_id is None:
            query = query.where(UserPreference.scope == "global")
        else:
            query = query.where(UserPreference.project_id == project_id)
        records = list(db.scalars(query.order_by(UserPreference.key.asc(), UserPreference.updated_at.desc(), UserPreference.id.desc())))
        deduped: dict[str, UserPreference] = {}
        for record in records:
            deduped.setdefault(record.key, record)
        return [record for key, record in sorted(deduped.items()) if self._is_active(record)]

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
        normalized_key = self._normalize_key(key)
        scope = "project" if project_id is not None else "global"
        matches = self._records_for_scope(db, key=normalized_key, project_id=project_id)
        record = matches[0] if matches else None
        if record is None:
            record = UserPreference(key=normalized_key, scope=scope, project_id=project_id)
            db.add(record)
        for duplicate in matches[1:]:
            db.delete(duplicate)
        record.value_json = value_json
        record.source = source
        record.editable = editable
        db.flush()
        return record

    def delete_preference(self, db: Session, *, key: str, project_id: int | None = None) -> bool:
        matches = self._records_for_scope(db, key=key, project_id=project_id)
        if not matches:
            return False
        for record in matches:
            db.delete(record)
        db.flush()
        return True

    def preference_summary(self, db: Session, project: Project | None = None) -> dict[str, Any]:
        records = self.get_effective_preferences(db, project) if project is not None else self.list_preferences(db, project_id=None)
        scope = "project" if project is not None else "global"
        items = [
            {
                "id": item.id,
                "key": item.key,
                "value_json": item.value_json,
                "source": item.source,
                "scope": item.scope,
                "project_id": item.project_id,
                "editable": item.editable,
                "created_at": item.created_at,
                "updated_at": item.updated_at,
                "inherited": project is not None and item.scope == "global",
            }
            for item in records
        ]
        return {
            "scope": scope,
            "project_id": project.id if project is not None else None,
            "items": items,
            "item_count": len(items),
            "editable_count": sum(1 for item in items if item["editable"]),
            "inherited_count": sum(1 for item in items if item["inherited"]),
            "project_override_count": sum(1 for item in items if item["scope"] == "project"),
        }


preference_service = PreferenceService()
