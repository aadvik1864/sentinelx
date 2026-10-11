"""Preserve replay acknowledgements when unlinked raw events expire."""

import sqlalchemy as sa
from alembic import op

revision = "0005_receipt_tombstones"
down_revision = "0004_account_security"
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    constraints = inspector.get_foreign_keys("source_receipts")
    convention = {"fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"}
    name = next(row["name"] for row in constraints if row["constrained_columns"] == ["event_id"])
    with op.batch_alter_table("source_receipts", naming_convention=convention) as batch:
        batch.drop_constraint(name or "fk_source_receipts_event_id_events", type_="foreignkey")


def downgrade():
    # Do not discard replay protection to make a downgrade fit. Restore a pre-retention backup instead.
    bind = op.get_bind()
    missing = bind.execute(
        sa.text(
            "SELECT COUNT(*) FROM source_receipts r LEFT JOIN events e ON e.id=r.event_id WHERE e.id IS NULL"
        )
    ).scalar_one()
    if missing:
        raise RuntimeError(
            "Receipt tombstones exist; restore a pre-retention backup before downgrade"
        )
    with op.batch_alter_table("source_receipts") as batch:
        batch.create_foreign_key(
            "fk_source_receipts_event_id_events", "events", ["event_id"], ["id"]
        )
