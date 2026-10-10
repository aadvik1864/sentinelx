from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.common import page, require_row, search, utc_filter
from app.core.database import get_db
from app.core.security import rate_limit, read_security, write_security
from app.models import Event, User
from app.schemas import EventInput, RawLog, Severity
from app.services.detection.engine import ingest
from app.services.ingestion.normalizer import normalize
from app.services.serialization import serialize

router = APIRouter(prefix="/events", tags=["Events"])


@router.get("")
def list_events(
    q: str = Query(default="", max_length=500),
    severity: Severity | None = None,
    source: str | None = None,
    source_id: int | None = Query(default=None, ge=1),
    event_type: str | None = None,
    source_ip: str | None = None,
    destination_ip: str | None = None,
    hostname: str | None = None,
    username: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0, le=100000),
    user: User = Depends(read_security),
    db: Session = Depends(get_db),
):
    query = select(Event)
    if source_id is not None:
        query = query.where(Event.details["source_id"].as_integer() == source_id)
    fields = {
        "severity",
        "source",
        "event_type",
        "source_ip",
        "destination_ip",
        "hostname",
        "username",
    }
    for key, value in {
        "severity": severity,
        "source": source,
        "event_type": event_type,
        "source_ip": source_ip,
        "destination_ip": destination_ip,
        "hostname": hostname,
        "username": username,
    }.items():
        if value is not None:
            query = query.where(getattr(Event, key) == value)
    if start_time:
        query = query.where(Event.timestamp >= utc_filter(start_time))
    if end_time:
        query = query.where(Event.timestamp <= utc_filter(end_time))
    query = search(query, Event, q, fields).order_by(Event.timestamp.desc(), Event.id.desc())
    return page(db, query, Event, limit, offset)


@router.post("", status_code=201)
def create_event(
    data: EventInput,
    request: Request,
    user: User = Depends(write_security),
    db: Session = Depends(get_db),
):
    rate_limit(request, "ingestion", 1200)
    return ingest(db, data)


@router.post("/raw", status_code=201)
def raw_event(
    data: RawLog,
    request: Request,
    user: User = Depends(write_security),
    db: Session = Depends(get_db),
):
    rate_limit(request, "ingestion", 1200)
    try:
        event = normalize(data)
    except (ValueError, ValidationError, KeyError, TypeError):
        raise HTTPException(
            422, "Log could not be normalized. Check the source format and timestamp."
        ) from None
    return ingest(db, event)


@router.get("/{event_id}")
def event_detail(event_id: int, user: User = Depends(read_security), db: Session = Depends(get_db)):
    return serialize(require_row(db, Event, event_id))
