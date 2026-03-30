"""Add missing scheduled-scan columns and performance indexes

Revision ID: 0008
Revises: 0007
Create Date: 2026-03-30 00:00:00.000000

Two concerns addressed in a single migration:

1. Missing schema columns
   The scheduled-scan feature (Track A #12) was merged without an Alembic
   migration, leaving `sites.schedule` and `sites.next_scan_at` absent from
   any migration-path database (they exist only in create_all deployments).
   This migration adds them when missing, using PRAGMA table_info to be
   idempotent.

2. Performance indexes
   No FK column had a dedicated index — every join/filter was a full table
   scan.  Indexes are created with IF NOT EXISTS so the migration is safe
   to run on both fresh (create_all) and migration-path databases.

   New indexes:
     scans(site_id)             – fetch all scans for a site
     scans(status)              – scheduler finds pending/running scans
     scans(created_at)          – date-range filtering in scan history
     scans(site_id, created_at) – paginated scan history per site (composite)
     issues(scan_id)            – fetch all issues for a scan
     issues(severity)           – filter/count issues by severity
     sites(user_id)             – fetch all sites for a user
     sites(next_scan_at)        – scheduler looks up sites due for scanning
   Plus indexes on audit_logs columns that only exist in the model, not in
   any prior migration.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(conn, table: str, column: str) -> bool:
    """Return True if *column* is already present in *table* (SQLite PRAGMA)."""
    rows = conn.execute(sa.text(f"PRAGMA table_info({table})")).fetchall()
    return any(row[1] == column for row in rows)


def _table_exists(conn, table: str) -> bool:
    result = conn.execute(
        sa.text("SELECT name FROM sqlite_master WHERE type='table' AND name=:t"),
        {"t": table},
    ).fetchone()
    return result is not None


def upgrade() -> None:
    conn = op.get_bind()

    # ------------------------------------------------------------------ #
    # 1. Backfill missing scheduled-scan columns on sites                 #
    # ------------------------------------------------------------------ #
    if not _column_exists(conn, "sites", "schedule"):
        op.add_column(
            "sites",
            sa.Column("schedule", sa.String(length=20), nullable=False, server_default="none"),
        )
    if not _column_exists(conn, "sites", "next_scan_at"):
        op.add_column(
            "sites",
            sa.Column("next_scan_at", sa.DateTime(), nullable=True),
        )

    # ------------------------------------------------------------------ #
    # 2. audit_logs table — only created by create_all in earlier         #
    #    versions; Alembic-path deployments need it explicitly.           #
    # ------------------------------------------------------------------ #
    if not _table_exists(conn, "audit_logs"):
        conn.execute(sa.text("""
            CREATE TABLE audit_logs (
                id            INTEGER NOT NULL PRIMARY KEY,
                user_id       INTEGER REFERENCES users(id) ON DELETE CASCADE,
                action        VARCHAR(64)  NOT NULL,
                resource_type VARCHAR(32),
                resource_id   INTEGER,
                ip_address    VARCHAR(45),
                user_agent    VARCHAR(256),
                extra         JSON,
                created_at    DATETIME DEFAULT (CURRENT_TIMESTAMP)
            )
        """))

    # api_keys table — same situation (added post-migration via create_all)
    if not _table_exists(conn, "api_keys"):
        conn.execute(sa.text("""
            CREATE TABLE api_keys (
                id           INTEGER NOT NULL PRIMARY KEY,
                user_id      INTEGER NOT NULL REFERENCES users(id),
                name         VARCHAR(100) NOT NULL,
                key_prefix   VARCHAR(12)  NOT NULL,
                key_hash     VARCHAR(64)  NOT NULL UNIQUE,
                expires_at   DATETIME,
                last_used_at DATETIME,
                created_at   DATETIME DEFAULT (CURRENT_TIMESTAMP)
            )
        """))

    # ------------------------------------------------------------------ #
    # 3. Performance indexes — IF NOT EXISTS keeps the migration safe.    #
    # ------------------------------------------------------------------ #
    index_stmts = [
        "CREATE INDEX IF NOT EXISTS ix_scans_site_id      ON scans(site_id)",
        "CREATE INDEX IF NOT EXISTS ix_scans_status       ON scans(status)",
        "CREATE INDEX IF NOT EXISTS ix_scans_created_at   ON scans(created_at)",
        "CREATE INDEX IF NOT EXISTS ix_scans_site_created ON scans(site_id, created_at)",
        "CREATE INDEX IF NOT EXISTS ix_issues_scan_id     ON issues(scan_id)",
        "CREATE INDEX IF NOT EXISTS ix_issues_severity    ON issues(severity)",
        "CREATE INDEX IF NOT EXISTS ix_sites_user_id      ON sites(user_id)",
        "CREATE INDEX IF NOT EXISTS ix_sites_next_scan_at ON sites(next_scan_at)",
        "CREATE INDEX IF NOT EXISTS ix_api_keys_user_id   ON api_keys(user_id)",
        "CREATE INDEX IF NOT EXISTS ix_audit_logs_id         ON audit_logs(id)",
        "CREATE INDEX IF NOT EXISTS ix_audit_logs_user_id    ON audit_logs(user_id)",
        "CREATE INDEX IF NOT EXISTS ix_audit_logs_action     ON audit_logs(action)",
        "CREATE INDEX IF NOT EXISTS ix_audit_logs_created_at ON audit_logs(created_at)",
    ]
    for stmt in index_stmts:
        conn.execute(sa.text(stmt))


def downgrade() -> None:
    conn = op.get_bind()
    drop_stmts = [
        "DROP INDEX IF EXISTS ix_scans_site_id",
        "DROP INDEX IF EXISTS ix_scans_status",
        "DROP INDEX IF EXISTS ix_scans_created_at",
        "DROP INDEX IF EXISTS ix_scans_site_created",
        "DROP INDEX IF EXISTS ix_issues_scan_id",
        "DROP INDEX IF EXISTS ix_issues_severity",
        "DROP INDEX IF EXISTS ix_sites_user_id",
        "DROP INDEX IF EXISTS ix_sites_next_scan_at",
        "DROP INDEX IF EXISTS ix_api_keys_user_id",
        "DROP INDEX IF EXISTS ix_audit_logs_id",
        "DROP INDEX IF EXISTS ix_audit_logs_user_id",
        "DROP INDEX IF EXISTS ix_audit_logs_action",
        "DROP INDEX IF EXISTS ix_audit_logs_created_at",
    ]
    for stmt in drop_stmts:
        conn.execute(sa.text(stmt))
    # Note: we do NOT drop audit_logs / api_keys tables on downgrade, nor
    # remove the added columns — data loss is worse than leftover schema.
