"""Expiring collector keys and transactional delivery. Existing keys are preserved."""

import sqlalchemy as sa
from alembic import op

revision = "0006_delivery_and_collectors"
down_revision = "0005_receipt_tombstones"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("log_sources") as batch:
        batch.add_column(sa.Column("token_expires_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("previous_token_hash", sa.String(64), nullable=True))
        batch.add_column(sa.Column("previous_token_expires_at", sa.DateTime(), nullable=True))
    op.create_table(
        "notification_outbox",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "alert_id", sa.Integer(), sa.ForeignKey("alerts.id"), nullable=False, unique=True
        ),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(), nullable=False),
        sa.Column("delivered_at", sa.DateTime(), nullable=True),
        sa.Column("lease_owner", sa.String(36), nullable=True),
        sa.Column("lease_until", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.String(40), nullable=False),
    )
    op.create_index("ix_outbox_pending", "notification_outbox", ["delivered_at", "next_attempt_at"])


def downgrade():
    raise RuntimeError(
        "Delivery history/key rotation cannot be silently discarded; restore a reviewed backup"
    )
