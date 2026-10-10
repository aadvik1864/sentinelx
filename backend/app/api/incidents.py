from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.common import page, require_row, search
from app.core.database import get_db
from app.core.security import audit, current_user, write_security
from app.models import (
    IOC,
    Alert,
    Event,
    Incident,
    IncidentEvent,
    IncidentIOC,
    IncidentNote,
    User,
    utcnow,
)
from app.schemas import (
    IncidentCreate,
    IncidentPatch,
    IncidentStatus,
    LinkEvents,
    NoteInput,
    Severity,
)
from app.services.detection.engine import link_event
from app.services.serialization import serialize
from app.websocket.broker import broker

router = APIRouter(prefix="/incidents", tags=["Incidents"])


def detail(db, incident):
    query = (
        select(Event)
        .join(IncidentEvent, Event.id == IncidentEvent.event_id)
        .where(IncidentEvent.incident_id == incident.id)
    )
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    events = db.scalars(query.order_by(Event.timestamp, Event.id).limit(500)).all()
    notes = db.execute(
        select(IncidentNote, User.name)
        .join(User, IncidentNote.user_id == User.id)
        .where(IncidentNote.incident_id == incident.id)
        .order_by(IncidentNote.created_at)
        .limit(500)
    ).all()
    iocs = db.scalars(
        select(IOC)
        .join(IncidentIOC, IOC.id == IncidentIOC.ioc_id)
        .where(IncidentIOC.incident_id == incident.id)
    ).all()
    assignee = db.get(User, incident.assigned_to) if incident.assigned_to else None
    return {
        **serialize(incident),
        "assigned_name": assignee.name if assignee else None,
        "events": [serialize(row) for row in events],
        "event_total": total,
        "evidence_truncated": total > 500,
        "alerts": [
            serialize(row)
            for row in db.scalars(select(Alert).where(Alert.incident_id == incident.id))
        ],
        "notes": [{**serialize(row), "author": name} for row, name in notes],
        "iocs": [serialize(row) for row in iocs],
    }


@router.get("")
def list_incidents(
    severity: Severity | None = None,
    status: IncidentStatus | None = None,
    q: str = Query(default="", max_length=500),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0, le=100000),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    query = select(Incident)
    if severity:
        query = query.where(Incident.severity == severity)
    if status:
        query = query.where(Incident.status == status)
    query = search(query, Incident, q, {"severity", "status", "source_ip", "hostname"}, "title")
    return page(
        db, query.order_by(Incident.updated_at.desc(), Incident.id.desc()), Incident, limit, offset
    )


@router.post("", status_code=201)
def create_incident(
    data: IncidentCreate,
    request: Request,
    user: User = Depends(write_security),
    db: Session = Depends(get_db),
):
    events = [require_row(db, Event, row_id) for row_id in set(data.event_ids)]
    alerts = [require_row(db, Alert, row_id) for row_id in set(data.alert_ids)]
    if any(alert.incident_id for alert in alerts):
        raise HTTPException(409, "An alert is already linked to an incident")
    incident = Incident(
        title=data.title,
        description=data.description,
        severity=data.severity,
        hostname=events[0].hostname if events else "",
        source_ip=events[0].source_ip if events else None,
    )
    db.add(incident)
    db.flush()
    for event in events:
        link_event(db, incident, event)
    for alert in alerts:
        alert.incident_id = incident.id
        link_event(db, incident, db.get(Event, alert.event_id))
        db.flush()
        incident.mitre_techniques = sorted(set(incident.mitre_techniques + alert.mitre_techniques))
    audit(db, user, "CREATE_INCIDENT", "incident", incident.id, request)
    db.commit()
    broker.publish("incidents", "new_incident", serialize(incident))
    return detail(db, incident)


@router.get("/{incident_id}")
def incident_detail(
    incident_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    return detail(db, require_row(db, Incident, incident_id))


@router.patch("/{incident_id}")
def update_incident(
    incident_id: int,
    data: IncidentPatch,
    request: Request,
    user: User = Depends(write_security),
    db: Session = Depends(get_db),
):
    incident = require_row(db, Incident, incident_id)
    values = data.model_dump(exclude_unset=True)
    if any(values.get(key) is None for key in values if key != "assigned_to"):
        raise HTTPException(422, "Only assigned_to can be null")
    if values.get("assigned_to"):
        assignee = require_row(db, User, values["assigned_to"])
        if assignee.role == "VIEWER":
            raise HTTPException(422, "Assign incidents to an analyst or administrator")
    before = {key: getattr(incident, key) for key in values}
    for key, value in values.items():
        setattr(incident, key, value)
    if "status" in values:
        incident.resolved_at = utcnow() if data.status == "resolved" else None
        # Resolution closes related non-false-positive alerts in the same transaction.
        if data.status == "resolved":
            for alert in db.scalars(
                select(Alert).where(
                    Alert.incident_id == incident.id, Alert.status != "false_positive"
                )
            ):
                alert.status = "resolved"
                db.flush()
    audit(
        db,
        user,
        "UPDATE_INCIDENT",
        "incident",
        incident_id,
        request,
        {"before": before, "after": values},
    )
    db.commit()
    broker.publish("incidents", "updated_incident", serialize(incident))
    broker.publish("alerts", "reconcile", {"incident_id": incident.id})
    return detail(db, incident)


@router.post("/{incident_id}/notes", status_code=201)
def add_note(
    incident_id: int,
    data: NoteInput,
    request: Request,
    user: User = Depends(write_security),
    db: Session = Depends(get_db),
):
    incident = require_row(db, Incident, incident_id)
    note = IncidentNote(
        incident_id=incident_id, user_id=user.id, content=data.content, kind=data.kind
    )
    db.add(note)
    incident.updated_at = utcnow()
    audit(db, user, "ADD_INCIDENT_NOTE", "incident", incident_id, request, {"kind": data.kind})
    db.commit()
    broker.publish("incidents", "updated_incident", serialize(incident))
    return {**serialize(note), "author": user.name}


@router.post("/{incident_id}/events")
def add_events(
    incident_id: int,
    data: LinkEvents,
    request: Request,
    user: User = Depends(write_security),
    db: Session = Depends(get_db),
):
    incident = require_row(db, Incident, incident_id)
    for row_id in set(data.event_ids):
        link_event(db, incident, require_row(db, Event, row_id))
    audit(
        db,
        user,
        "LINK_INCIDENT_EVENTS",
        "incident",
        incident_id,
        request,
        {"event_ids": data.event_ids},
    )
    db.commit()
    broker.publish("incidents", "updated_incident", serialize(incident))
    return detail(db, incident)
