"""Source-scoped collection credentials, health, and transactional replay receipts."""

import sqlalchemy as sa
from alembic import op

revision = "0003_log_sources"
down_revision = "0002_refresh_consumption"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "log_sources",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("hostname", sa.String(253), nullable=False),
        sa.Column("log_path", sa.String(512), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_heartbeat_at", sa.DateTime()),
        sa.Column("last_event_at", sa.DateTime()),
        sa.Column("last_event_timestamp", sa.DateTime()),
        sa.Column("last_error", sa.String(300), nullable=False),
        sa.Column("total_events", sa.Integer(), nullable=False),
    )
    op.create_table(
        "source_receipts",
        sa.Column("source_id", sa.Integer(), sa.ForeignKey("log_sources.id"), primary_key=True),
        sa.Column("record_key", sa.String(128), primary_key=True),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("event_id", sa.Integer(), sa.ForeignKey("events.id"), nullable=False),
        sa.Column("incident_id", sa.Integer(), sa.ForeignKey("incidents.id")),
    )
    op.create_index("ix_source_receipts_event_id", "source_receipts", ["event_id"])


def downgrade():
    op.drop_table("source_receipts")
    op.drop_table("log_sources")
