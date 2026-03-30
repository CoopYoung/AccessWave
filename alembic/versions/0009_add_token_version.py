"""Add token_version column to users for JWT revocation

Revision ID: 0009
Revises: 0008
Create Date: 2026-03-30 00:00:00.000000

Adds a `token_version` integer column to the users table.  Every JWT issued
for a user embeds the current token_version.  When `get_current_user` validates
a JWT it checks that the embedded version matches the user's current version.

Incrementing `token_version` (via POST /api/auth/logout or /api/auth/logout-all)
immediately invalidates all previously issued tokens for that user without
needing a separate blacklist table.
"""

from alembic import op
import sqlalchemy as sa


revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # SQLite-compatible: add column only if it doesn't already exist
    conn = op.get_bind()
    cols = [row[1] for row in conn.execute(sa.text("PRAGMA table_info(users)")).fetchall()]
    if "token_version" not in cols:
        op.add_column("users", sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    # SQLite does not support DROP COLUMN on older versions; skip silently
    try:
        op.drop_column("users", "token_version")
    except Exception:
        pass
