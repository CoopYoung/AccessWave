"""Add email notification preferences to users

Revision ID: 0003
Revises: 0002
Create Date: 2026-03-30 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("email_notify_on_complete", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("users", sa.Column("email_notify_on_failure", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("users", sa.Column("email_score_threshold", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "email_score_threshold")
    op.drop_column("users", "email_notify_on_failure")
    op.drop_column("users", "email_notify_on_complete")
