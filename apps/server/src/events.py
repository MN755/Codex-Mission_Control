from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncGenerator

from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from db import SessionLocal, session_scope
from models import AppEvent, ProjectEvent


class EventService:
    def publish(self, db: Session, project_id: int, event_type: str, payload: dict) -> ProjectEvent:
        event = ProjectEvent(project_id=project_id, event_type=event_type, payload_json=payload)
        db.add(event)
        db.flush()
        app_payload = {"project_id": project_id, **dict(payload or {})}
        db.add(AppEvent(event_type=event_type, payload_json=app_payload))
        db.flush()
        return event

    def list_events(self, db: Session, project_id: int, after_id: int | None = None) -> list[ProjectEvent]:
        query = select(ProjectEvent).where(ProjectEvent.project_id == project_id).order_by(ProjectEvent.id.asc())
        if after_id is not None:
            query = query.where(ProjectEvent.id > after_id)
        return list(db.scalars(query))

    def publish_app(self, db: Session, event_type: str, payload: dict) -> AppEvent:
        event = AppEvent(event_type=event_type, payload_json=payload)
        db.add(event)
        db.flush()
        return event

    def publish_isolated(self, project_id: int, event_type: str, payload: dict, *, retries: int = 5, delay_seconds: float = 0.05) -> bool:
        for attempt in range(retries):
            try:
                with session_scope() as db:
                    self.publish(db, project_id, event_type, payload)
                return True
            except OperationalError as exc:
                if "database is locked" not in str(exc).lower():
                    raise
                if attempt >= retries - 1:
                    return False
                time.sleep(delay_seconds * (attempt + 1))
        return False

    def list_app_events(self, db: Session, after_id: int | None = None) -> list[AppEvent]:
        query = select(AppEvent).order_by(AppEvent.id.asc())
        if after_id is not None:
            query = query.where(AppEvent.id > after_id)
        return list(db.scalars(query))

    async def stream(self, project_id: int, after_id: int | None = None) -> AsyncGenerator[str, None]:
        last_id = after_id or 0
        while True:
            session = SessionLocal()
            try:
                events = self.list_events(session, project_id, last_id)
                if events:
                    for event in events:
                        payload = {
                            "id": event.id,
                            "type": event.event_type,
                            "created_at": event.created_at.isoformat(),
                            "payload": event.payload_json,
                        }
                        last_id = event.id
                        yield f"id: {event.id}\ndata: {json.dumps(payload)}\n\n"
                else:
                    yield ": heartbeat\n\n"
            finally:
                session.close()
            await asyncio.sleep(1)

    async def stream_app(self, after_id: int | None = None) -> AsyncGenerator[str, None]:
        last_id = after_id or 0
        while True:
            session = SessionLocal()
            try:
                events = self.list_app_events(session, last_id)
                if events:
                    for event in events:
                        payload = {
                            "id": event.id,
                            "type": event.event_type,
                            "created_at": event.created_at.isoformat(),
                            "payload": event.payload_json,
                        }
                        last_id = event.id
                        yield f"id: {event.id}\ndata: {json.dumps(payload)}\n\n"
                else:
                    yield ": heartbeat\n\n"
            finally:
                session.close()
            await asyncio.sleep(1)
