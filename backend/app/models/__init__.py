from datetime import UTC, datetime

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.base import Base


def utcnow():
    return datetime.now(UTC).replace(tzinfo=None)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="VIEWER")
    auth_version: Mapped[int] = mapped_column(default=0)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False)
    disabled: Mapped[bool] = mapped_column(Boolean, default=False)
    mfa_secret: Mapped[str | None] = mapped_column(Text)
    mfa_pending_secret: Mapped[str | None] = mapped_column(Text)
    mfa_pending_expires_at: Mapped[datetime | None] = mapped_column(DateTime)
    mfa_last_step: Mapped[int] = mapped_column(Integer, default=-1)
    mfa_recovery_hashes: Mapped[list] = mapped_column(JSON, default=list)
    mfa_webauthn_handle: Mapped[str | None] = mapped_column(String(64))
    passkeys: Mapped[list["WebAuthnCredential"]] = relationship(lazy="selectin")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class RefreshSession(Base):
    __tablename__ = "refresh_sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    family: Mapped[str] = mapped_column(String(36), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    consumed: Mapped[bool] = mapped_column(Boolean, default=False)
    mfa_verified: Mapped[bool] = mapped_column(Boolean, default=False)


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (
        Index("ix_event_detection", "source_ip", "hostname", "event_type", "timestamp"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, index=True)
    source: Mapped[str] = mapped_column(String(30), index=True)
    event_type: Mapped[str] = mapped_column(String(100), index=True)
    severity: Mapped[str] = mapped_column(String(20), index=True)
    source_ip: Mapped[str | None] = mapped_column(String(45), index=True)
    destination_ip: Mapped[str | None] = mapped_column(String(45))
    username: Mapped[str | None] = mapped_column(String(100))
    hostname: Mapped[str] = mapped_column(String(253), index=True)
    message: Mapped[str] = mapped_column(Text)
    details: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class LogSource(Base):
    __tablename__ = "log_sources"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    kind: Mapped[str] = mapped_column(String(30))
    hostname: Mapped[str] = mapped_column(String(253))
    log_path: Mapped[str] = mapped_column(String(512), default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    token_hash: Mapped[str] = mapped_column(String(64))
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime)
    previous_token_hash: Mapped[str | None] = mapped_column(String(64))
    previous_token_expires_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_event_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_event_timestamp: Mapped[datetime | None] = mapped_column(DateTime)
    last_error: Mapped[str] = mapped_column(String(300), default="")
    total_events: Mapped[int] = mapped_column(Integer, default=0)


class SourceReceipt(Base):
    __tablename__ = "source_receipts"
    source_id: Mapped[int] = mapped_column(ForeignKey("log_sources.id"), primary_key=True)
    record_key: Mapped[str] = mapped_column(String(128), primary_key=True)
    payload_hash: Mapped[str] = mapped_column(String(64))
    # Stable acknowledgement ID, retained as a replay tombstone after raw-log retention.
    event_id: Mapped[int] = mapped_column(Integer, index=True)
    incident_id: Mapped[int | None] = mapped_column(ForeignKey("incidents.id"))


class DetectionRule(Base):
    __tablename__ = "detection_rules"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150), unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    kind: Mapped[str] = mapped_column(String(50), default="threshold")
    event_type: Mapped[str] = mapped_column(String(100))
    threshold: Mapped[int] = mapped_column(Integer, default=10)
    window_seconds: Mapped[int] = mapped_column(Integer, default=300)
    severity: Mapped[str] = mapped_column(String(20), default="high")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    mitre_techniques: Mapped[list] = mapped_column(JSON, default=list)
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class Incident(Base):
    __tablename__ = "incidents"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    severity: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(30), default="open", index=True)
    assigned_to: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    source_ip: Mapped[str | None] = mapped_column(String(45), index=True)
    hostname: Mapped[str] = mapped_column(String(253), default="")
    mitre_techniques: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime)


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (
        Index("ix_alert_suppression", "rule_id", "source_ip", "hostname", "detected_at"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"))
    rule_id: Mapped[int | None] = mapped_column(
        ForeignKey("detection_rules.id", ondelete="SET NULL")
    )
    incident_id: Mapped[int | None] = mapped_column(ForeignKey("incidents.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(20), index=True)
    source_ip: Mapped[str | None] = mapped_column(String(45))
    hostname: Mapped[str] = mapped_column(String(253))
    status: Mapped[str] = mapped_column(String(30), default="open", index=True)
    event_count: Mapped[int] = mapped_column(default=1)
    mitre_techniques: Mapped[list] = mapped_column(JSON, default=list)
    detected_at: Mapped[datetime] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class IncidentEvent(Base):
    __tablename__ = "incident_events"
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidents.id"), primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), primary_key=True)


class IncidentNote(Base):
    __tablename__ = "incident_notes"
    id: Mapped[int] = mapped_column(primary_key=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidents.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    content: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(20), default="note")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Asset(Base):
    __tablename__ = "assets"
    id: Mapped[int] = mapped_column(primary_key=True)
    hostname: Mapped[str] = mapped_column(String(253), unique=True)
    ip_address: Mapped[str] = mapped_column(String(45))
    type: Mapped[str] = mapped_column(String(30), default="server")
    environment: Mapped[str] = mapped_column(String(30), default="lab")
    owner: Mapped[str] = mapped_column(String(100), default="Security operations")
    status: Mapped[str] = mapped_column(String(30), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class IOC(Base):
    __tablename__ = "iocs"
    __table_args__ = (Index("ix_ioc_type_value", "type", "value", unique=True),)
    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[str] = mapped_column(String(20))
    value: Mapped[str] = mapped_column(String(253))
    reputation: Mapped[str] = mapped_column(String(30))
    confidence: Mapped[int | None] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(50))
    first_seen: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_seen: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    details: Mapped[dict] = mapped_column("metadata", JSON, default=dict)


class IncidentIOC(Base):
    __tablename__ = "incident_iocs"
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidents.id"), primary_key=True)
    ioc_id: Mapped[int] = mapped_column(ForeignKey("iocs.id"), primary_key=True)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(80))
    resource: Mapped[str] = mapped_column(String(50))
    resource_id: Mapped[str] = mapped_column(String(100))
    ip_address: Mapped[str | None] = mapped_column(String(45))
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    details: Mapped[dict] = mapped_column("metadata", JSON, default=dict)


class NotificationOutbox(Base):
    __tablename__ = "notification_outbox"
    __table_args__ = (Index("ix_outbox_pending", "delivered_at", "next_attempt_at"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    alert_id: Mapped[int] = mapped_column(ForeignKey("alerts.id"), unique=True)
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime)
    lease_owner: Mapped[str | None] = mapped_column(String(36))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime)
    last_error: Mapped[str] = mapped_column(String(40), default="")


class WebAuthnCredential(Base):
    __tablename__ = "webauthn_credentials"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    credential_id: Mapped[str] = mapped_column(String(2048), unique=True)
    public_key: Mapped[str] = mapped_column(Text)
    sign_count: Mapped[int] = mapped_column(BigInteger, default=0)
    name: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime)


class WebAuthnChallenge(Base):
    __tablename__ = "webauthn_challenges"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    challenge: Mapped[str] = mapped_column(String(64))
    auth_version: Mapped[int] = mapped_column(Integer)
    origin: Mapped[str] = mapped_column(String(300))
    expires_at: Mapped[datetime] = mapped_column(DateTime)
