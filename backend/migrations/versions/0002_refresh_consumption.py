"""Separate refresh-token consumption from session revocation for multiple browser tabs."""

import sqlalchemy as sa
from alembic import op

revision = "0002_refresh_consumption"
down_revision = "8d4f1860c20c"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "refresh_sessions",
        sa.Column("consumed", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade():
    op.drop_column("refresh_sessions", "consumed")
