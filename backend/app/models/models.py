from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Company(Base, TimestampMixin):
    __tablename__ = 'companies'
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100), index=True)
    market: Mapped[str] = mapped_column(String(20), default='A')
    status: Mapped[str] = mapped_column(String(20), default='watching')
    holding_cost: Mapped[float | None] = mapped_column(Float)
    target_price: Mapped[float | None] = mapped_column(Float)
    thesis: Mapped[str | None] = mapped_column(Text)
    disproof_conditions: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)


class BusinessLine(Base, TimestampMixin):
    __tablename__ = 'business_lines'
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey('companies.id'), index=True)
    name: Mapped[str] = mapped_column(String(100))
    role: Mapped[str | None] = mapped_column(String(50))
    description: Mapped[str | None] = mapped_column(Text)
    keywords: Mapped[list[str] | None] = mapped_column(JSON)
    key_metrics: Mapped[str | None] = mapped_column(Text)


class Announcement(Base, TimestampMixin):
    __tablename__ = 'announcements'
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey('companies.id'), index=True)
    title: Mapped[str] = mapped_column(String(255), index=True)
    publish_time: Mapped[datetime] = mapped_column(DateTime, index=True)
    source: Mapped[str | None] = mapped_column(String(50))
    url: Mapped[str | None] = mapped_column(String(500))
    category: Mapped[str | None] = mapped_column(String(50))
    importance_score: Mapped[int] = mapped_column(Integer, default=0)
    is_risk_event: Mapped[bool] = mapped_column(Boolean, default=False)
    is_business_update: Mapped[bool] = mapped_column(Boolean, default=False)
    related_business_lines: Mapped[list[str] | None] = mapped_column(JSON)
    need_manual_review: Mapped[bool] = mapped_column(Boolean, default=False)
    summary: Mapped[str | None] = mapped_column(Text)
    raw_text: Mapped[str | None] = mapped_column(Text)
    content_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    logic_impact: Mapped[str | None] = mapped_column(String(20))
    evidence_type: Mapped[str | None] = mapped_column(String(50))
    ai_confidence: Mapped[str | None] = mapped_column(String(20))
    ai_reason: Mapped[str | None] = mapped_column(Text)
    ai_analyzed_at: Mapped[datetime | None] = mapped_column(DateTime)
    prompt_version: Mapped[str | None] = mapped_column(String(50))


class NewsItem(Base, TimestampMixin):
    __tablename__ = 'news_items'
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255), index=True)
    source: Mapped[str | None] = mapped_column(String(50))
    url: Mapped[str | None] = mapped_column(String(500))
    publish_time: Mapped[datetime] = mapped_column(DateTime, index=True)
    company_id: Mapped[int | None] = mapped_column(ForeignKey('companies.id'), index=True)
    category: Mapped[str | None] = mapped_column(String(50))
    importance_score: Mapped[int] = mapped_column(Integer, default=0)
    is_risk_event: Mapped[bool] = mapped_column(Boolean, default=False)
    is_business_update: Mapped[bool] = mapped_column(Boolean, default=False)
    related_business_lines: Mapped[list[str] | None] = mapped_column(JSON)
    need_manual_review: Mapped[bool] = mapped_column(Boolean, default=False)
    summary: Mapped[str | None] = mapped_column(Text)
    raw_text: Mapped[str | None] = mapped_column(Text)
    content_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    logic_impact: Mapped[str | None] = mapped_column(String(20))
    evidence_type: Mapped[str | None] = mapped_column(String(50))
    ai_confidence: Mapped[str | None] = mapped_column(String(20))
    ai_reason: Mapped[str | None] = mapped_column(Text)
    ai_analyzed_at: Mapped[datetime | None] = mapped_column(DateTime)
    prompt_version: Mapped[str | None] = mapped_column(String(50))


class RiskEvent(Base, TimestampMixin):
    __tablename__ = 'risk_events'
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int | None] = mapped_column(ForeignKey('companies.id'))
    event_type: Mapped[str] = mapped_column(String(50))
    level: Mapped[str] = mapped_column(String(20), default='low')
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    evidence: Mapped[str | None] = mapped_column(Text)
    source_type: Mapped[str] = mapped_column(String(20))
    source_id: Mapped[int | None] = mapped_column(Integer)
    is_resolved: Mapped[bool] = mapped_column(Boolean, default=False)


class Report(Base, TimestampMixin):
    __tablename__ = 'reports'
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int | None] = mapped_column(ForeignKey('companies.id'))
    report_type: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(255))
    period: Mapped[str | None] = mapped_column(String(50))
    markdown_content: Mapped[str] = mapped_column(Text)
    conclusion: Mapped[str | None] = mapped_column(Text)
    risk_level: Mapped[str | None] = mapped_column(String(20))


class AITask(Base, TimestampMixin):
    __tablename__ = 'ai_tasks'
    id: Mapped[int] = mapped_column(primary_key=True)
    task_type: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(20), default='pending')
    provider: Mapped[str | None] = mapped_column(String(50))
    model: Mapped[str | None] = mapped_column(String(100))
    input_ref_type: Mapped[str | None] = mapped_column(String(50))
    input_ref_id: Mapped[int | None] = mapped_column(Integer)
    output_ref_type: Mapped[str | None] = mapped_column(String(50))
    output_ref_id: Mapped[int | None] = mapped_column(Integer)
    error_message: Mapped[str | None] = mapped_column(Text)
    token_usage: Mapped[str | None] = mapped_column(String(255))
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)


class SourceRecord(Base, TimestampMixin):
    __tablename__ = 'source_records'
    id: Mapped[int] = mapped_column(primary_key=True)
    source_type: Mapped[str] = mapped_column(String(20))
    source_name: Mapped[str] = mapped_column(String(100))
    title: Mapped[str | None] = mapped_column(String(255))
    url: Mapped[str | None] = mapped_column(String(500))
    publish_time: Mapped[datetime | None] = mapped_column(DateTime)
    raw_content: Mapped[str | None] = mapped_column(Text)
    content_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class BusinessLineEvidence(Base, TimestampMixin):
    __tablename__ = 'business_line_evidence'
    __table_args__ = (UniqueConstraint('source_type', 'source_id', 'business_line_id', name='uq_evidence_source_bl'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey('companies.id'), index=True)
    business_line_id: Mapped[int | None] = mapped_column(ForeignKey('business_lines.id'), index=True)
    source_type: Mapped[str] = mapped_column(String(20))
    source_id: Mapped[int] = mapped_column(Integer)
    evidence_type: Mapped[str] = mapped_column(String(50), default='other')
    direction: Mapped[str] = mapped_column(String(20), default='uncertain')
    logic_impact: Mapped[str] = mapped_column(String(20), default='uncertain')
    title: Mapped[str] = mapped_column(String(255))
    summary: Mapped[str | None] = mapped_column(Text)
    reason: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[str] = mapped_column(String(20), default='low')
    need_manual_review: Mapped[bool] = mapped_column(Boolean, default=False)
