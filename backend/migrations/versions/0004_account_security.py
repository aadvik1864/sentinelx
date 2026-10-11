"""Add account security without changing existing passwords, roles, or evidence."""

import sqlalchemy as sa
from alembic import op

revision = "0004_account_security"
down_revision = "0003_log_sources"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "users", sa.Column("disabled", sa.Boolean(), nullable=False, server_default=sa.false())
    )
    op.add_column(
        "users",
        sa.Column("must_change_password", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("users", sa.Column("mfa_secret", sa.Text()))
    op.add_column("users", sa.Column("mfa_pending_secret", sa.Text()))
    op.add_column("users", sa.Column("mfa_pending_expires_at", sa.DateTime()))
    op.add_column(
        "users", sa.Column("mfa_last_step", sa.Integer(), nullable=False, server_default="-1")
    )
    op.add_column(
        "users", sa.Column("mfa_recovery_hashes", sa.JSON(), nullable=False, server_default="[]")
    )
    op.add_column(
        "refresh_sessions",
        sa.Column("mfa_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade():
    op.drop_column("refresh_sessions", "mfa_verified")
    for column in (
        "mfa_recovery_hashes",
        "mfa_last_step",
        "mfa_pending_expires_at",
        "mfa_pending_secret",
        "mfa_secret",
        "must_change_password",
        "disabled",
    ):
        op.drop_column("users", column)
