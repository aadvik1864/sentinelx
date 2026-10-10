from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.common import require_row
from app.core.database import get_db
from app.core.security import audit, rate_limit, write_security
from app.models import Event, Incident, IncidentEvent, IncidentIOC, User
from app.services.serialization import serialize
from app.services.threat_intel.providers import lookup
from app.websocket.broker import broker

router = APIRouter(tags=["Threat intelligence"])


@router.get("/threat-intelligence/{kind}/{value}")
def indicator_lookup(
    kind: str,
    value: str,
    request: Request,
    user: User = Depends(write_security),
    db: Session = Depends(get_db),
):
    rate_limit(request, "intel", 20)
    row = lookup(db, kind, value)
    audit(db, user, "IOC_LOOKUP", "ioc", row.id, request, {"type": kind, "value": row.value})
    db.commit()
    return serialize(row)


@router.post("/incidents/{incident_id}/enrich")
def enrich_incident(
    incident_id: int,
    request: Request,
    user: User = Depends(write_security),
    db: Session = Depends(get_db),
):
    rate_limit(request, "intel", 20)
    incident = require_row(db, Incident, incident_id)
    ips = db.scalars(
        select(Event.source_ip)
        .join(IncidentEvent, Event.id == IncidentEvent.event_id)
        .where(IncidentEvent.incident_id == incident_id, Event.source_ip.is_not(None))
        .distinct()
        .limit(20)
    ).all()
    results = []
    for ip in ips:
        row = lookup(db, "ip", ip)
        if not db.get(IncidentIOC, (incident_id, row.id)):
            db.add(IncidentIOC(incident_id=incident_id, ioc_id=row.id))
        results.append(serialize(row))
    audit(db, user, "ENRICH_INCIDENT", "incident", incident_id, request)
    db.commit()
    broker.publish("incidents", "updated_incident", serialize(incident))
    return {"items": results}
