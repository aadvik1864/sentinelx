from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.common import page, require_row, search
from app.core.database import get_db
from app.core.security import audit, current_user, write_security
from app.models import Alert, DetectionRule, Event, User
from app.schemas import AlertPatch, AlertStatus, Severity
from app.services.serialization import serialize
from app.websocket.broker import broker

router = APIRouter(prefix="/alerts", tags=["Alerts"])


@router.get("")
def list_alerts(
    severity: Severity | None = None,
    status: AlertStatus | None = None,
    q: str = Query(default="", max_length=500),
    source_ip: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0, le=100000),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    query = select(Alert)
    for key, value in {"severity": severity, "status": status, "source_ip": source_ip}.items():
        if value:
            query = query.where(getattr(Alert, key) == value)
    query = search(query, Alert, q, {"severity", "status", "source_ip", "hostname"}, "title")
    return page(db, query.order_by(Alert.created_at.desc(), Alert.id.desc()), Alert, limit, offset)


@router.get("/{alert_id}")
def alert_detail(alert_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    alert = require_row(db, Alert, alert_id)
    rule = db.get(DetectionRule, alert.rule_id) if alert.rule_id else None
    return {
        **serialize(alert),
        "event": serialize(db.get(Event, alert.event_id)),
        "rule": serialize(rule) if rule else None,
    }


@router.patch("/{alert_id}")
def update_alert(
    alert_id: int,
    data: AlertPatch,
    request: Request,
    user: User = Depends(write_security),
    db: Session = Depends(get_db),
):
    alert = require_row(db, Alert, alert_id)
    before = alert.status
    alert.status = data.status
    audit(
        db,
        user,
        "UPDATE_ALERT",
        "alert",
        alert_id,
        request,
        {"before": before, "after": data.status},
    )
    db.commit()
    broker.publish("alerts", "updated_alert", serialize(alert))
    return serialize(alert)
