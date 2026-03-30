import datetime
import uuid
from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text, JSON
from sqlalchemy.orm import relationship
from app.database import Base


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    plan = Column(String(20), default="free")
    stripe_customer_id = Column(String(255), nullable=True)
    stripe_subscription_id = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    # Email notification preferences
    email_notify_on_complete = Column(Boolean, default=False, nullable=False, server_default="0")
    email_notify_on_failure = Column(Boolean, default=False, nullable=False, server_default="0")
    # Notify when score drops at or below this threshold (null = disabled)
    email_score_threshold = Column(Float, nullable=True)
    # Email verification
    email_verified = Column(Boolean, default=False, nullable=False, server_default="0")
    # TOTP-based two-factor authentication
    totp_secret = Column(String(64), nullable=True)    # base32 TOTP secret
    totp_enabled = Column(Boolean, default=False, nullable=False, server_default="0")
    # Account lockout after repeated failed logins
    failed_login_attempts = Column(Integer, default=0, nullable=False, server_default="0")
    locked_until = Column(DateTime, nullable=True)
    sites = relationship("Site", back_populates="owner", cascade="all, delete-orphan")
    api_keys = relationship("ApiKey", back_populates="user", cascade="all, delete-orphan")
    webhooks = relationship("Webhook", back_populates="user", cascade="all, delete-orphan")


class Site(Base):
    __tablename__ = "sites"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    url = Column(String(2048), nullable=False)
    name = Column(String(255), nullable=False)
    # Scheduled scanning: none | daily | weekly | monthly
    schedule = Column(String(20), default="none", nullable=False)
    next_scan_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    owner = relationship("User", back_populates="sites")
    scans = relationship("Scan", back_populates="site", cascade="all, delete-orphan")


class Scan(Base):
    __tablename__ = "scans"
    id = Column(Integer, primary_key=True, index=True)
    site_id = Column(Integer, ForeignKey("sites.id"), nullable=False)
    status = Column(String(20), default="pending")  # pending, running, completed, failed
    pages_scanned = Column(Integer, default=0)
    total_issues = Column(Integer, default=0)
    critical_count = Column(Integer, default=0)
    serious_count = Column(Integer, default=0)
    moderate_count = Column(Integer, default=0)
    minor_count = Column(Integer, default=0)
    score = Column(Float, nullable=True)  # 0-100 accessibility score
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    share_token = Column(String(36), nullable=True, unique=True, index=True)  # UUID for public share links
    site = relationship("Site", back_populates="scans")
    issues = relationship("Issue", back_populates="scan", cascade="all, delete-orphan")


class Issue(Base):
    __tablename__ = "issues"
    id = Column(Integer, primary_key=True, index=True)
    scan_id = Column(Integer, ForeignKey("scans.id"), nullable=False)
    page_url = Column(String(2048), nullable=False)
    rule_id = Column(String(50), nullable=False)
    severity = Column(String(20), nullable=False)  # critical, serious, moderate, minor
    wcag_criteria = Column(String(20), nullable=True)  # e.g. "1.1.1", "4.1.2"
    message = Column(Text, nullable=False)
    element_html = Column(Text, nullable=True)
    selector = Column(String(500), nullable=True)
    how_to_fix = Column(Text, nullable=True)
    scan = relationship("Scan", back_populates="issues")


class Webhook(Base):
    __tablename__ = "webhooks"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    url = Column(String(2048), nullable=False)
    # HMAC-SHA256 signing secret — shown once at creation, stored in plaintext
    # so users can verify incoming payloads on their servers.
    secret = Column(String(64), nullable=False)
    # JSON list of subscribed event types, e.g. ["scan.completed", "scan.failed"]
    events = Column(JSON, nullable=False, default=list)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    user = relationship("User", back_populates="webhooks")


class ApiKey(Base):
    __tablename__ = "api_keys"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String(100), nullable=False)
    # First 11 chars of the raw key (e.g. "aw_abc12345") shown in UI after creation
    key_prefix = Column(String(12), nullable=False)
    # SHA-256 hex digest of the full raw key — never stored in plaintext
    key_hash = Column(String(64), nullable=False, unique=True, index=True)
    expires_at = Column(DateTime, nullable=True)
    last_used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    user = relationship("User", back_populates="api_keys")


class AuditLog(Base):
    """Immutable record of security-relevant user actions."""
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True, index=True)
    # Nullable so failed logins (unknown user) can still be recorded
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    action = Column(String(64), nullable=False, index=True)   # e.g. "login.success"
    resource_type = Column(String(32), nullable=True)         # e.g. "site", "scan"
    resource_id = Column(Integer, nullable=True)
    ip_address = Column(String(45), nullable=True)            # IPv4 or IPv6
    user_agent = Column(String(256), nullable=True)
    extra = Column(JSON, nullable=True)                       # arbitrary extra context
    created_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)
