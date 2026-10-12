"""Add optional verified WebAuthn second factors without changing existing identities."""

import sqlalchemy as sa
from alembic import op

revision = "0007_passkeys"
down_revision = "0006_delivery_and_collectors"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("mfa_webauthn_handle", sa.String(64), nullable=True))
    op.create_table(
        "webauthn_credentials",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("credential_id", sa.String(2048), nullable=False, unique=True),
        sa.Column("public_key", sa.Text(), nullable=False),
        sa.Column("sign_count", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_webauthn_credentials_user_id", "webauthn_credentials", ["user_id"])
    op.create_table(
        "webauthn_challenges",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("challenge", sa.String(64), nullable=False),
        sa.Column("auth_version", sa.Integer(), nullable=False),
        sa.Column("origin", sa.String(300), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_webauthn_challenges_user_id", "webauthn_challenges", ["user_id"])


def downgrade():
    raise RuntimeError("Removing enrolled credentials requires a reviewed recovery plan")
