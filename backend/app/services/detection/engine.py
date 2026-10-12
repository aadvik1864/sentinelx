import hashlib
import threading
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models import (
    Alert,
    DetectionRule,
    Event,
    Incident,
    IncidentEvent,
    LogSource,
    NotificationOutbox,
    SourceReceipt,
    utcnow,
)
from app.schemas import EventInput
from app.services.redaction import redact
from app.services.serialization import serialize
from app.websocket.broker import broker

SEVERITY_RANK = {"low": 0, "medium": 1, "high": 2, "critical": 3}
ingestion_lock = threading.RLock()


def correlated_incident(db: Session, event: Event):
    if not event.source_ip:
        return None
    return db.scalar(
        select(Incident)
        .where(
            Incident.source_ip == event.source_ip,
            Incident.hostname == event.hostname,
            Incident.status != "resolved",
            Incident.last_seen_at >= event.timestamp - timedelta(minutes=30),
            Incident.created_at <= event.created_at,
        )
        .order_by(Incident.id.desc())
    )


def link_event(db: Session, incident: Incident, event: Event):
    if not db.get(IncidentEvent, (incident.id, event.id)):
        db.add(IncidentEvent(incident_id=incident.id, event_id=event.id))
    incident.last_seen_at = max(incident.last_seen_at, event.timestamp)


def rule_evidence(db: Session, rule: DetectionRule, event: Event) -> list[Event]:
    if rule.config.get("sources") and event.source not in rule.config["sources"]:
        return []
    if event.event_type != rule.event_type:
        return []
    if not event.source_ip and rule.kind != "privilege_escalation":
        return []
    # Source and target are both part of the grouping key; failures on host A must not accuse host B.
    rows = list(
        db.scalars(
            select(Event)
            .where(
                Event.source_ip == event.source_ip,
                Event.hostname == event.hostname,
                Event.timestamp >= event.timestamp - timedelta(seconds=rule.window_seconds),
                Event.timestamp <= event.timestamp,
            )
            .order_by(Event.timestamp, Event.id)
        )
    )
    if rule.config.get("sources"):
        rows = [row for row in rows if row.source in rule.config["sources"]]
    if rule.kind == "threshold":
        evidence = [row for row in rows if row.event_type == rule.event_type]
        return evidence if len(evidence) >= rule.threshold else []
    if rule.kind in {"successful_after_failures", "suspicious_authentication"}:
        failures = [
            row
            for row in rows
            if row.event_type in {"authentication_failure", "invalid_user"}
            and row.timestamp <= event.timestamp
            and row.username == event.username
        ]
        if len(failures) < rule.threshold:
            return []
        if rule.kind == "suspicious_authentication" and not any(
            row.event_type == "invalid_user" or row.details.get("invalid_user") is True
            for row in failures
        ):
            return []
        return failures + [event]
    if rule.kind == "privilege_escalation":
        return [event]
    if rule.kind == "port_scan":
        connections = [row for row in rows if row.event_type == rule.event_type]
        ports = {row.details.get("destination_port") for row in connections} - {None}
        return connections if len(ports) >= rule.threshold else []
    if rule.kind == "http_errors":
        requests = [row for row in rows if row.event_type == rule.event_type]
        errors = [row for row in requests if row.details.get("http_status", 0) >= 400]
        if len(requests) >= rule.threshold and len(errors) / len(requests) >= rule.config.get(
            "error_ratio", 0.3
        ):
            return requests
    return []


def ingest(
    db: Session,
    data: EventInput,
    source: LogSource | None = None,
    record_key: str | None = None,
    payload_hash: str | None = None,
):
    updates = []
    with ingestion_lock:
        if source:
            # SQLite ignores FOR UPDATE; reload counters after taking the process lock.
            db.refresh(source)
        if source and record_key:
            receipt = db.get(SourceReceipt, (source.id, record_key))
            if receipt:
                if receipt.payload_hash != payload_hash:
                    raise ValueError("Record key was reused with different content")
                db.commit()
                return {
                    "event": {"id": receipt.event_id},
                    "alerts": [],
                    "incident_id": receipt.incident_id,
                    "duplicate": True,
                }
        if db.bind.dialect.name == "postgresql":
            key = int.from_bytes(
                hashlib.sha256(f"{data.source_ip}:{data.hostname}".encode()).digest()[:8],
                "big",
                signed=True,
            )
            db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})
        safe = data.model_copy(
            update={"message": redact(data.message), "metadata": redact(data.metadata)}
        )
        event = Event(
            **safe.model_dump(exclude={"metadata", "source_ip", "destination_ip", "timestamp"}),
            timestamp=data.timestamp.replace(tzinfo=None),
            source_ip=str(data.source_ip) if data.source_ip else None,
            destination_ip=str(data.destination_ip) if data.destination_ip else None,
            details=safe.metadata,
        )
        db.add(event)
        db.flush()
        alerts = []
        incident = correlated_incident(db, event)
        if incident:
            link_event(db, incident, event)
        for rule in db.scalars(select(DetectionRule).where(DetectionRule.enabled.is_(True))).all():
            evidence = rule_evidence(db, rule, event)
            if not evidence:
                continue
            # Suppress repetitions for a rule/group for its configured event-time window.
            previous = db.scalar(
                select(Alert)
                .where(
                    Alert.rule_id == rule.id,
                    Alert.source_ip == event.source_ip,
                    Alert.hostname == event.hostname,
                    Alert.detected_at >= event.timestamp - timedelta(seconds=rule.window_seconds),
                    Alert.detected_at <= event.timestamp + timedelta(seconds=rule.window_seconds),
                )
                .order_by(Alert.id.desc())
            )
            if previous:
                previous.event_count = max(previous.event_count, len(evidence))
                updates.append(("alerts", "updated_alert", previous))
                continue
            if not incident:
                incident = Incident(
                    title=f"{rule.name} on {event.hostname}",
                    description="Automatically correlated by source IP and target host.",
                    severity=rule.severity,
                    source_ip=event.source_ip,
                    hostname=event.hostname,
                    last_seen_at=event.timestamp,
                    mitre_techniques=rule.mitre_techniques,
                )
                db.add(incident)
                db.flush()
            elif SEVERITY_RANK[rule.severity] > SEVERITY_RANK[incident.severity]:
                incident.severity = rule.severity
                if rule.severity == "critical":
                    incident.title = f"Possible account compromise on {event.hostname}"
            incident.mitre_techniques = sorted(
                set(incident.mitre_techniques + rule.mitre_techniques)
            )
            for item in evidence:
                link_event(db, incident, item)
                db.flush()
            alert = Alert(
                event_id=event.id,
                rule_id=rule.id,
                incident_id=incident.id,
                title=rule.name,
                description=f"{len(evidence)} matching events in a {rule.window_seconds}s window on {event.hostname}.",
                severity=rule.severity,
                source_ip=event.source_ip,
                hostname=event.hostname,
                event_count=len(evidence),
                mitre_techniques=rule.mitre_techniques,
                detected_at=event.timestamp,
            )
            db.add(alert)
            db.flush()
            alerts.append(alert)
            # Committed with the alert, not a best-effort request made after commit.
            db.add(
                NotificationOutbox(
                    id=str(uuid4()),
                    alert_id=alert.id,
                    payload={
                        "alert_id": alert.id,
                        "severity": alert.severity,
                        "incident_id": alert.incident_id,
                    },
                )
            )
            updates.append(("alerts", "new_alert", alert))
        if source:
            source.last_heartbeat_at = utcnow()
            source.last_event_at = utcnow()
            source.last_event_timestamp = event.timestamp
            source.last_error = ""
            source.total_events += 1
            db.add(
                SourceReceipt(
                    source_id=source.id,
                    record_key=record_key,
                    payload_hash=payload_hash,
                    event_id=event.id,
                    incident_id=incident.id if incident else None,
                )
            )
        db.commit()
        # Broadcast only committed rows; reconnecting clients reconcile through paginated REST.
        for channel, kind, row in updates:
            broker.publish(channel, kind, serialize(row))
        broker.publish("events", "new_event", serialize(event))
        if incident:
            broker.publish("incidents", "updated_incident", serialize(incident))
        return {
            "event": serialize(event),
            "alerts": [serialize(row) for row in alerts],
            "incident_id": incident.id if incident else None,
        }
