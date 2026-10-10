from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.common import require_row
from app.core.database import get_db
from app.core.security import audit, rate_limit, write_security
from app.models import Alert, Incident, User
from app.schemas import AnalyzeIncident, ExplainAlert
from app.services.ai.analyzer import alert_context, analyze, incident_context

router = APIRouter(prefix="/ai", tags=["SOC assistant"])


@router.post("/analyze-incident")
def analyze_incident(
    data: AnalyzeIncident,
    request: Request,
    user: User = Depends(write_security),
    db: Session = Depends(get_db),
):
    rate_limit(request, "ai", 10)
    incident = require_row(db, Incident, data.incident_id)
    result = analyze(incident_context(db, incident))
    audit(db, user, "ANALYZE_INCIDENT", "incident", incident.id, request, {"mode": result["mode"]})
    db.commit()
    return result


@router.post("/explain-alert")
def explain_alert(
    data: ExplainAlert,
    request: Request,
    user: User = Depends(write_security),
    db: Session = Depends(get_db),
):
    rate_limit(request, "ai", 10)
    alert = require_row(db, Alert, data.alert_id)
    result = analyze(alert_context(db, alert))
    audit(db, user, "EXPLAIN_ALERT", "alert", alert.id, request, {"mode": result["mode"]})
    db.commit()
    return result
