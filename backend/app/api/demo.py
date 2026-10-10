import ipaddress
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import admin_only, audit, rate_limit
from app.models import User
from app.seed import attack_sequence
from app.services.detection.engine import ingest

router = APIRouter(prefix="/demo", tags=["Isolated lab"])


@router.post("/simulate")
def simulate(request: Request, user: User = Depends(admin_only), db: Session = Depends(get_db)):
    settings = get_settings()
    if settings.environment != "development" or not settings.demo_mode:
        raise HTTPException(404, "Simulation is disabled")
    rate_limit(request, "simulation", 3)
    # This only inserts synthetic records. It never connects to or attacks the represented IPs.
    address = str(ipaddress.ip_address("203.0.113.0") + secrets.randbelow(250) + 1)
    incident_id, event_ids, alert_ids = None, [], []
    for event in attack_sequence(source_ip=address):
        result = ingest(db, event)
        event_ids.append(result["event"]["id"])
        alert_ids.extend(row["id"] for row in result["alerts"])
        incident_id = result["incident_id"] or incident_id
    audit(db, user, "RUN_LAB_SIMULATION", "incident", incident_id, request)
    db.commit()
    return {
        "incident_id": incident_id,
        "event_ids": event_ids,
        "alert_ids": alert_ids,
        "simulated": True,
    }
