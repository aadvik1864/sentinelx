import hashlib
import hmac
import json
import secrets
from datetime import timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import admin_only, audit, bearer, limiter, read_security, token_digest
from app.models import LogSource, User, utcnow
from app.schemas import (
    RawLog,
    SourceHeartbeat,
    SourceInput,
    SourcePatch,
    SourceRecord,
    SourceRotation,
)
from app.services.detection.engine import ingest
from app.services.ingestion.normalizer import normalize
from app.services.serialization import serialize

router = APIRouter(prefix="/sources", tags=["Log sources"])
ERRORS = {
    "file_unavailable": "The collector cannot read its configured log file. Check the path and read permissions.",
    "docker_unavailable": "The configured container is not running or its logs are not readable.",
    "record_rejected": "A log record was rejected and saved in the collector's private quarantine. Check its format.",
    "connection_failed": "The collector cannot reach SentinelX. It will retry without advancing its checkpoint.",
    "configuration_error": "The collector configuration needs attention.",
    "log_gap": "Logs rotated or disappeared before they could be read. A collection gap requires review.",
}


def source_view(source):
    result = serialize(source)
    if not source.enabled:
        status = "paused"
    elif source.token_expires_at and source.token_expires_at <= utcnow():
        status = "key_expired"
    elif not source.last_heartbeat_at:
        status = "not_connected"
    elif (utcnow() - source.last_heartbeat_at).total_seconds() > 90:
        status = "offline"
    elif source.last_error:
        status = "error"
    elif source.last_event_at and (utcnow() - source.last_event_at).total_seconds() < 90:
        status = "receiving"
    else:
        status = "waiting"
    result["status"] = status
    return result


@router.get("")
def list_sources(user: User = Depends(read_security), db: Session = Depends(get_db)):
    return {
        "items": [source_view(row) for row in db.scalars(select(LogSource).order_by(LogSource.id))]
    }


@router.get("/agent")
def download_agent(user: User = Depends(read_security)):
    roots = [Path(__file__).resolve().parents[2], Path(__file__).resolve().parents[3]]
    for root in roots:
        path = root / "collectors" / "agent.py"
        if path.is_file():
            return FileResponse(path, media_type="text/x-python", filename="sentinelx-agent.py")
    raise HTTPException(503, "Collector download is unavailable")


@router.post("", status_code=201)
def create_source(
    data: SourceInput,
    request: Request,
    user: User = Depends(admin_only),
    db: Session = Depends(get_db),
):
    token = "sxcol_" + secrets.token_urlsafe(32)
    source = LogSource(
        **data.model_dump(),
        token_hash=token_digest(token),
        token_expires_at=utcnow() + timedelta(days=90),
    )
    db.add(source)
    db.flush()
    audit(db, user, "CREATE_LOG_SOURCE", "log_source", source.id, request)
    db.commit()
    return {"source": source_view(source), "collector_key": token}


@router.patch("/{source_id}")
def update_source(
    source_id: int,
    data: SourcePatch,
    request: Request,
    user: User = Depends(admin_only),
    db: Session = Depends(get_db),
):
    source = db.get(LogSource, source_id)
    if not source:
        raise HTTPException(404, "Log source not found")
    source.enabled = data.enabled
    audit(
        db, user, "UPDATE_LOG_SOURCE", "log_source", source.id, request, {"enabled": data.enabled}
    )
    db.commit()
    return source_view(source)


@router.post("/{source_id}/rotate-key")
def rotate_key(
    source_id: int,
    request: Request,
    user: User = Depends(admin_only),
    db: Session = Depends(get_db),
    data: SourceRotation = SourceRotation(),
):
    source = db.scalar(select(LogSource).where(LogSource.id == source_id).with_for_update())
    if not source:
        raise HTTPException(404, "Log source not found")
    token = "sxcol_" + secrets.token_urlsafe(32)
    now = utcnow()
    source.previous_token_hash = source.token_hash if data.overlap_seconds else None
    source.previous_token_expires_at = (
        (
            min(now + timedelta(seconds=data.overlap_seconds), source.token_expires_at)
            if source.token_expires_at
            else now + timedelta(seconds=data.overlap_seconds)
        )
        if data.overlap_seconds
        else None
    )
    source.token_hash = token_digest(token)
    source.token_expires_at = now + timedelta(days=data.valid_days)
    audit(
        db,
        user,
        "ROTATE_COLLECTOR_KEY",
        "log_source",
        source.id,
        request,
        {"overlap_seconds": data.overlap_seconds, "valid_days": data.valid_days},
    )
    db.commit()
    return {"source": source_view(source), "collector_key": token}


def collector_source(
    source_id: int,
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
):
    source = db.scalar(select(LogSource).where(LogSource.id == source_id).with_for_update())
    now = utcnow()
    digest = token_digest(credentials.credentials) if credentials else ""
    current_valid = bool(
        source
        and credentials
        and hmac.compare_digest(source.token_hash, digest)
        and (source.token_expires_at is None or source.token_expires_at > now)
    )
    previous_valid = bool(
        source
        and credentials
        and source.previous_token_hash
        and source.previous_token_expires_at
        and source.previous_token_expires_at > now
        and hmac.compare_digest(source.previous_token_hash, digest)
    )
    if not source or not credentials or not (current_valid or previous_valid):
        limiter.check(
            f"invalid-collector:{request.client.host if request.client else 'unknown'}", 60
        )
        raise HTTPException(401, "Invalid collector credential")
    if not source.enabled:
        raise HTTPException(403, "Log source is paused")
    return source


@router.post("/{source_id}/heartbeat")
def heartbeat(
    data: SourceHeartbeat,
    source: LogSource = Depends(collector_source),
    db: Session = Depends(get_db),
):
    limiter.check(f"collector-heartbeat:{source.id}", 20)
    source.last_heartbeat_at = utcnow()
    source.last_error = (
        ERRORS.get(data.error, "Collector reported an error.") if data.state == "error" else ""
    )
    db.commit()
    return {"status": "ok"}


@router.post("/{source_id}/events", status_code=201)
def collect_record(
    data: SourceRecord, source: LogSource = Depends(collector_source), db: Session = Depends(get_db)
):
    limiter.check(f"collector-ingestion:{source.id}", 1200)
    try:
        # Collection must never present receipt time as the occurrence timestamp.
        if source.kind == "linux" and data.timestamp is None:
            raise ValueError("Linux collector must supply the occurrence timestamp")
        if source.kind == "application" or data.line.lstrip().startswith("{"):
            parsed = json.loads(data.line)
            if not isinstance(parsed, dict) or not (data.timestamp or parsed.get("timestamp")):
                raise ValueError("JSON collector record requires an occurrence timestamp")
        event = normalize(
            RawLog(
                source=source.kind,
                hostname=source.hostname,
                line=data.line,
                timestamp=data.timestamp,
            )
        )
    except (ValueError, ValidationError, KeyError, TypeError):
        raise HTTPException(
            422, "Log could not be normalized. Check its format and occurrence timestamp."
        ) from None
    event.metadata.update({"source_id": source.id, "simulated": False, "provenance": "collector"})
    digest = hashlib.sha256(
        json.dumps(data.model_dump(mode="json"), sort_keys=True).encode()
    ).hexdigest()
    try:
        result = ingest(db, event, source=source, record_key=data.record_key, payload_hash=digest)
    except ValueError:
        raise HTTPException(409, "Record key was reused with different content") from None
    return {"event_id": result["event"]["id"], "duplicate": result.get("duplicate", False)}
