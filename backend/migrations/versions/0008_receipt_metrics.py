"""Index receipt-minute metrics without rewriting event times or evidence."""

from alembic import op

revision = "0008_receipt_metrics"
down_revision = "0007_passkeys"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index("ix_events_created_at", "events", ["created_at"])


def downgrade():
    op.drop_index("ix_events_created_at", "events")
