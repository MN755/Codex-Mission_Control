from __future__ import annotations

import asyncio
import json

from sqlalchemy import select

from conftest import sample_workspace
from db import SessionLocal
from main import stream_dashboard, stream_events
from models import AppEvent, ProjectEvent


def create_project(client, name: str, workspace_name: str) -> dict:
    response = client.post(
        "/api/projects",
        json={
            "name": name,
            "idea": f"{name} idea",
            "workspace_path": sample_workspace(workspace_name),
            "provider": "codex",
            "runner_mode": "dry_run",
            "manager_mode": "auto",
        },
    )
    assert response.status_code == 200
    return response.json()


async def read_first_sse_event(response) -> tuple[int, dict]:
    event_id: int | None = None
    try:
        while True:
            chunk = await anext(response.body_iterator)
            text = chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk
            for line in text.splitlines():
                if not line or line.startswith(":"):
                    continue
                if line.startswith("id:"):
                    event_id = int(line.split(":", 1)[1].strip())
                    continue
                if line.startswith("data:"):
                    payload = json.loads(line.split(":", 1)[1].strip())
                    if event_id is None:
                        raise AssertionError("SSE payload arrived before event id.")
                    return event_id, payload
    finally:
        aclose = getattr(response.body_iterator, "aclose", None)
        if callable(aclose):
            await aclose()
    raise AssertionError("No SSE event payload was received.")


def test_dashboard_stream_returns_sse_payload_shape(client) -> None:
    created = client.post(
        "/api/dashboard/widgets/add",
        json={"widget_type": "Connected Accounts", "area": "dashboard_bottom"},
    )
    assert created.status_code == 200

    db = SessionLocal()
    try:
        event = db.scalar(select(AppEvent).where(AppEvent.event_type == "widget_instances_updated").order_by(AppEvent.id.desc()))
        assert event is not None
        expected_event_id = event.id
    finally:
        db.close()

    response = asyncio.run(stream_dashboard(after_id=expected_event_id - 1))
    assert response.media_type == "text/event-stream"
    sse_id, payload = asyncio.run(read_first_sse_event(response))

    assert sse_id == expected_event_id
    assert payload["id"] == expected_event_id
    assert payload["type"] == "widget_instances_updated"
    assert isinstance(payload["created_at"], str)
    assert payload["payload"]["scope"] == "dashboard"
    assert payload["payload"]["widget_type"] == "Connected Accounts"
    assert payload["payload"]["action"] == "created"


def test_project_stream_returns_sse_payload_shape(client) -> None:
    project = create_project(client, "Stream Project", "stream-project")
    project_id = project["id"]

    created = client.post(
        f"/api/projects/{project_id}/widgets/add",
        json={"widget_type": "Confidence Tracker", "area": "project_right_sidebar"},
    )
    assert created.status_code == 200

    db = SessionLocal()
    try:
        event = db.scalar(
            select(ProjectEvent)
            .where(
                ProjectEvent.project_id == project_id,
                ProjectEvent.event_type == "widget_instances_updated",
            )
            .order_by(ProjectEvent.id.desc())
        )
        assert event is not None
        expected_event_id = event.id
    finally:
        db.close()

    db = SessionLocal()
    try:
        response = asyncio.run(stream_events(project_id, after_id=expected_event_id - 1, db=db))
        assert response.media_type == "text/event-stream"
        sse_id, payload = asyncio.run(read_first_sse_event(response))
    finally:
        db.close()

    assert sse_id == expected_event_id
    assert payload["id"] == expected_event_id
    assert payload["type"] == "widget_instances_updated"
    assert isinstance(payload["created_at"], str)
    assert payload["payload"]["project_id"] == project_id
    assert payload["payload"]["scope"] == "project"
    assert payload["payload"]["widget_type"] == "Confidence Tracker"
    assert payload["payload"]["action"] == "created"
