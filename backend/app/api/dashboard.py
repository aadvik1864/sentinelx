from datetime import timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import current_user
from app.models import Alert, Asset, Event, Incident, User, utcnow

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("")
def dashboard(user: User = Depends(current_user), db: Session = Depends(get_db)):
    now = utcnow()
    since = now - timedelta(hours=24)
    active = Alert.status.not_in(["resolved", "false_positive"])

    def count(model, *conditions):
        return db.scalar(select(func.count()).select_from(model).where(*conditions))

    severity = dict(
        db.execute(
            select(Alert.severity, func.count()).where(active).group_by(Alert.severity)
        ).all()
    )
    if db.bind.dialect.name == "postgresql":
        bucket = func.date_trunc("hour", Event.timestamp)
    else:
        bucket = func.strftime("%Y-%m-%d %H:00:00", Event.timestamp)
    rows = db.execute(
        select(bucket, func.count())
        .where(Event.timestamp >= since)
        .group_by(bucket)
        .order_by(bucket)
    ).all()
    counts = {str(time)[:13]: total for time, total in rows}
    activity = []
    # A rolling 24-hour interval can span 25 clock-hour buckets (two partial endpoints).
    for hour in range(25):
        time = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=24 - hour)
        activity.append(
            {"timestamp": time.isoformat() + "Z", "events": counts.get(str(time)[:13], 0)}
        )
    top_ips = db.execute(
        select(Event.source_ip, func.count())
        .where(Event.timestamp >= since, Event.source_ip.is_not(None))
        .group_by(Event.source_ip)
        .order_by(func.count().desc())
        .limit(5)
    ).all()
    types = db.execute(
        select(Event.event_type, func.count())
        .where(Event.timestamp >= since)
        .group_by(Event.event_type)
        .order_by(func.count().desc())
        .limit(5)
    ).all()
    return {
        "total_events": count(Event, Event.timestamp >= since),
        "events_per_second": round(
            count(Event, Event.created_at >= now - timedelta(minutes=1)) / 60, 2
        ),
        "active_alerts": count(Alert, active),
        "critical_alerts": severity.get("critical", 0),
        "open_incidents": count(Incident, Incident.status != "resolved"),
        "resolved_incidents": count(Incident, Incident.status == "resolved"),
        "monitored_assets": count(Asset, Asset.status == "active"),
        "unique_source_ips": db.scalar(
            select(func.count(func.distinct(Event.source_ip))).where(Event.timestamp >= since)
        ),
        "severity_counts": {
            key: severity.get(key, 0) for key in ["critical", "high", "medium", "low"]
        },
        "activity": activity,
        "top_ips": [{"ip": ip, "count": total} for ip, total in top_ips],
        "event_types": [{"type": kind, "count": total} for kind, total in types],
        "time_range": "24h",
    }
