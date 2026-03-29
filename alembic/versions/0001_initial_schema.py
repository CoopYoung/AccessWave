"""Initial schema: users, sites, scans, issues

Revision ID: 0001
Revises:
Create Date: 2026-03-28 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("plan", sa.String(length=20), nullable=True),
        sa.Column("stripe_customer_id", sa.String(length=255), nullable=True),
        sa.Column("stripe_subscription_id", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)
    op.create_index(op.f("ix_users_id"), "users", ["id"], unique=False)

    op.create_table(
        "sites",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_sites_id"), "sites", ["id"], unique=False)

    op.create_table(
        "scans",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("site_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=True),
        sa.Column("pages_scanned", sa.Integer(), nullable=True),
        sa.Column("total_issues", sa.Integer(), nullable=True),
        sa.Column("critical_count", sa.Integer(), nullable=True),
        sa.Column("serious_count", sa.Integer(), nullable=True),
        sa.Column("moderate_count", sa.Integer(), nullable=True),
        sa.Column("minor_count", sa.Integer(), nullable=True),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_scans_id"), "scans", ["id"], unique=False)

    op.create_table(
        "issues",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("scan_id", sa.Integer(), nullable=False),
        sa.Column("page_url", sa.String(length=2048), nullable=False),
        sa.Column("rule_id", sa.String(length=50), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("wcag_criteria", sa.String(length=20), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("element_html", sa.Text(), nullable=True),
        sa.Column("selector", sa.String(length=500), nullable=True),
        sa.Column("how_to_fix", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["scan_id"], ["scans.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_issues_id"), "issues", ["id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_issues_id"), table_name="issues")
    op.drop_table("issues")

    op.drop_index(op.f("ix_scans_id"), table_name="scans")
    op.drop_table("scans")

    op.drop_index(op.f("ix_sites_id"), table_name="sites")
    op.drop_table("sites")

    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_index(op.f("ix_users_id"), table_name="users")
    op.drop_table("users")
