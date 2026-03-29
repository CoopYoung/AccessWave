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
    totp_secret = Column(String(32), nullable=True)
    totp_enabled = Column(Boolean, default=False, nullable=False)
    sites = relationship("Site", back_populates="owner", cascade="all, delete-orphan")
    api_keys = relationship("ApiKey", back_populates="user", cascade="all, delete-orphan")


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
