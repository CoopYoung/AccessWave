"""Add totp_recovery_codes column to users for 2FA recovery

Revision ID: 0011
Revises: 0010
Create Date: 2026-03-30 00:00:00.000000

Adds a JSON column that stores SHA-256 hashed one-time recovery codes.
When 2FA is enabled, 8 codes are generated and stored here. Each code
can only be used once; used codes are removed from the list.
"""

from alembic import op
import sqlalchemy as sa


revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    cols = [row[1] for row in conn.execute(sa.text("PRAGMA table_info(users)")).fetchall()]
    if "totp_recovery_codes" not in cols:
        op.add_column("users", sa.Column("totp_recovery_codes", sa.JSON(), nullable=True))


def downgrade() -> None:
    try:
        op.drop_column("users", "totp_recovery_codes")
    except Exception:
        pass
