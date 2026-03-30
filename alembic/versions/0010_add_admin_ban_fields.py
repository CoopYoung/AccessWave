"""Add is_admin and is_banned columns to users for admin dashboard

Revision ID: 0010
Revises: 0009
Create Date: 2026-03-30 00:00:00.000000

Adds two boolean columns to the users table:
  - is_admin: marks users who can access the /admin dashboard and
              admin API endpoints (GET /api/admin/*).
  - is_banned: prevents banned users from authenticating (login
               and API key use both return 403 Forbidden).
"""

from alembic import op
import sqlalchemy as sa


revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    cols = [row[1] for row in conn.execute(sa.text("PRAGMA table_info(users)")).fetchall()]
    if "is_admin" not in cols:
        op.add_column("users", sa.Column("is_admin", sa.Boolean(), nullable=False, server_default="0"))
    if "is_banned" not in cols:
        op.add_column("users", sa.Column("is_banned", sa.Boolean(), nullable=False, server_default="0"))


def downgrade() -> None:
    try:
        op.drop_column("users", "is_admin")
    except Exception:
        pass
    try:
        op.drop_column("users", "is_banned")
    except Exception:
        pass
