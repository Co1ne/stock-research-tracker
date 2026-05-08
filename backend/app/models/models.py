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
    industry: Mapped[str | None] = mapped_column(String(100))
    main_business: Mapped[str | None] = mapped_column(Text)
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
    confidence: Mapped[str | None] = mapped_column(String(20))
    generated_by: Mapped[str | None] = mapped_column(String(20))


class Announcement(Base, TimestampMixin):
    __tablename__ = 'announcements'
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey('companies.id'), index=True)
    title: Mapped[str] = mapped_column(String(255), index=True)
    publish_time: Mapped[datetime] = mapped_column(DateTime, index=True)
    source: Mapped[str | None] = mapped_column(String(50))
    source_name: Mapped[str | None] = mapped_column(String(100))
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
    ingestion_run_id: Mapped[int | None] = mapped_column(Integer, index=True)
    raw_payload: Mapped[dict | None] = mapped_column(JSON)
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
    source_name: Mapped[str | None] = mapped_column(String(100))
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
    ingestion_run_id: Mapped[int | None] = mapped_column(Integer, index=True)
    raw_payload: Mapped[dict | None] = mapped_column(JSON)
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
    hypothesis_id: Mapped[int | None] = mapped_column(ForeignKey('investment_hypotheses.id'), index=True)
    risk_event_id: Mapped[int | None] = mapped_column(ForeignKey('risk_events.id'), index=True)
    source_type: Mapped[str] = mapped_column(String(20))
    source_name: Mapped[str | None] = mapped_column(String(100))
    source_id: Mapped[int] = mapped_column(Integer)
    source_title: Mapped[str | None] = mapped_column(String(255))
    source_url: Mapped[str | None] = mapped_column(String(500))
    source_date: Mapped[datetime | None] = mapped_column(DateTime)
    evidence_type: Mapped[str] = mapped_column(String(50), default='other')
    direction: Mapped[str] = mapped_column(String(20), default='uncertain')
    logic_impact: Mapped[str] = mapped_column(String(20), default='uncertain')
    severity: Mapped[str] = mapped_column(String(20), default='low')
    title: Mapped[str] = mapped_column(String(255))
    summary: Mapped[str | None] = mapped_column(Text)
    reason: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[str] = mapped_column(String(20), default='rule')
    review_status: Mapped[str] = mapped_column(String(20), default='pending')
    need_manual_review: Mapped[bool] = mapped_column(Boolean, default=False)
    ai_summary: Mapped[str | None] = mapped_column(Text)
    ai_impact_judgment: Mapped[str | None] = mapped_column(String(20))
    ai_reason: Mapped[str | None] = mapped_column(Text)
    ai_confidence: Mapped[str | None] = mapped_column(String(20))
    ai_generated_at: Mapped[datetime | None] = mapped_column(DateTime)
    manual_override: Mapped[bool] = mapped_column(Boolean, default=False)
    manual_note: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime)
    reviewer: Mapped[str | None] = mapped_column(String(100))
    review_note: Mapped[str | None] = mapped_column(Text)
    original_content: Mapped[str | None] = mapped_column(Text)
    edited_content: Mapped[str | None] = mapped_column(Text)
    hypothesis_relation: Mapped[str] = mapped_column(String(20), default='watch')
    impact_strength: Mapped[str] = mapped_column(String(20), default='low')
    affected_aspect: Mapped[str] = mapped_column(String(50), default='other')
    evidence_summary: Mapped[str | None] = mapped_column(Text)
    relation_note: Mapped[str | None] = mapped_column(Text)
    ingestion_run_id: Mapped[int | None] = mapped_column(Integer, index=True)
    raw_payload: Mapped[dict | None] = mapped_column(JSON)
    content_hash: Mapped[str | None] = mapped_column(String(64), index=True)


class InvestmentHypothesis(Base, TimestampMixin):
    __tablename__ = 'investment_hypotheses'
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey('companies.id'), index=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    related_business_line_ids: Mapped[list[int] | None] = mapped_column(JSON)
    falsification_conditions: Mapped[list[str] | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default='unverified')
    review_status: Mapped[str] = mapped_column(String(20), default='pending')
    latest_evidence_summary: Mapped[str | None] = mapped_column(Text)
    generated_by: Mapped[str] = mapped_column(String(20), default='rule')
    thesis: Mapped[str | None] = mapped_column(Text)
    business_lines: Mapped[list[dict] | None] = mapped_column(JSON, default=list)
    watch_metrics: Mapped[list[str] | None] = mapped_column(JSON, default=list)
    positive_evidence_rules: Mapped[list[str] | None] = mapped_column(JSON, default=list)
    negative_evidence_rules: Mapped[list[str] | None] = mapped_column(JSON, default=list)
    invalidation_conditions: Mapped[list[str] | None] = mapped_column(JSON, default=list)
    current_view: Mapped[str] = mapped_column(String(20), default='neutral')
    tracking_priority: Mapped[str] = mapped_column(String(20), default='medium')
    note: Mapped[str | None] = mapped_column(Text)


class FinancialSnapshot(Base, TimestampMixin):
    __tablename__ = 'financial_snapshots'
    __table_args__ = (UniqueConstraint('company_id', 'report_period', name='uq_financial_company_period'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey('companies.id'), index=True)
    stock_code: Mapped[str] = mapped_column(String(20), index=True)
    report_period: Mapped[str] = mapped_column(String(50), index=True)
    revenue: Mapped[float | None] = mapped_column(Float)
    net_profit: Mapped[float | None] = mapped_column(Float)
    net_profit_deducted: Mapped[float | None] = mapped_column(Float)
    gross_margin: Mapped[float | None] = mapped_column(Float)
    net_margin: Mapped[float | None] = mapped_column(Float)
    operating_cash_flow: Mapped[float | None] = mapped_column(Float)
    accounts_receivable: Mapped[float | None] = mapped_column(Float)
    inventory: Mapped[float | None] = mapped_column(Float)
    debt_asset_ratio: Mapped[float | None] = mapped_column(Float)
    roe: Mapped[float | None] = mapped_column(Float)
    source: Mapped[str | None] = mapped_column(String(50))
    source_name: Mapped[str | None] = mapped_column(String(100))
    raw_data: Mapped[dict | None] = mapped_column(JSON)
    ingestion_run_id: Mapped[int | None] = mapped_column(Integer, index=True)


class IngestionRun(Base, TimestampMixin):
    __tablename__ = 'ingestion_runs'
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int | None] = mapped_column(ForeignKey('companies.id'), index=True)
    source_name: Mapped[str] = mapped_column(String(100), index=True)
    source_type: Mapped[str] = mapped_column(String(50), index=True)
    status: Mapped[str] = mapped_column(String(20), default='success', index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    items_found: Mapped[int] = mapped_column(Integer, default=0)
    items_created: Mapped[int] = mapped_column(Integer, default=0)
    items_updated: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)
    raw_error: Mapped[str | None] = mapped_column(Text)
    request_params: Mapped[dict | None] = mapped_column(JSON)
    result_summary: Mapped[dict | None] = mapped_column(JSON)


class ResearchNote(Base, TimestampMixin):
    __tablename__ = 'research_notes'
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey('companies.id'), index=True)
    hypothesis_id: Mapped[int | None] = mapped_column(ForeignKey('investment_hypotheses.id'), index=True)
    title: Mapped[str] = mapped_column(String(255))
    note_type: Mapped[str] = mapped_column(String(50), default='manual_note', index=True)
    conclusion_direction: Mapped[str] = mapped_column(String(20), default='watch', index=True)
    summary: Mapped[str | None] = mapped_column(Text)
    content: Mapped[str | None] = mapped_column(Text)
    cited_evidence_ids: Mapped[list[int] | None] = mapped_column(JSON, default=list)
    evidence_count: Mapped[int] = mapped_column(Integer, default=0)
    reviewed_evidence_count: Mapped[int] = mapped_column(Integer, default=0)
    unreviewed_evidence_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default='active', index=True)


class DisciplineCheck(Base, TimestampMixin):
    __tablename__ = 'discipline_checks'
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey('companies.id'), index=True)
    hypothesis_id: Mapped[int | None] = mapped_column(ForeignKey('investment_hypotheses.id'), index=True)
    title: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(20), default='draft', index=True)
    discipline_result: Mapped[str] = mapped_column(String(20), default='blocked', index=True)
    thesis_snapshot: Mapped[str | None] = mapped_column(Text)
    action_reason: Mapped[str | None] = mapped_column(Text)
    position_plan: Mapped[str | None] = mapped_column(Text)
    max_position_pct: Mapped[float | None] = mapped_column(Float)
    risk_acknowledgement: Mapped[str | None] = mapped_column(Text)
    invalidation_plan: Mapped[str | None] = mapped_column(Text)
    checklist: Mapped[dict | None] = mapped_column(JSON, default=dict)
    cited_evidence_ids: Mapped[list[int] | None] = mapped_column(JSON, default=list)
    cited_research_note_ids: Mapped[list[int] | None] = mapped_column(JSON, default=list)
    evidence_count: Mapped[int] = mapped_column(Integer, default=0)
    reviewed_evidence_count: Mapped[int] = mapped_column(Integer, default=0)
    unreviewed_evidence_count: Mapped[int] = mapped_column(Integer, default=0)
    rejected_evidence_count: Mapped[int] = mapped_column(Integer, default=0)
    blockers: Mapped[list[str] | None] = mapped_column(JSON, default=list)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)


class JobRun(Base, TimestampMixin):
    __tablename__ = 'job_runs'
    id: Mapped[int] = mapped_column(primary_key=True)
    job_name: Mapped[str] = mapped_column(String(100), index=True)
    status: Mapped[str] = mapped_column(String(20), default='running', index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    result_summary: Mapped[dict | None] = mapped_column(JSON)
    error_message: Mapped[str | None] = mapped_column(Text)
