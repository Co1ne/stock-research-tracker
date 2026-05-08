from sqlalchemy import inspect, text


def ensure_compatible_schema(engine):
    inspector = inspect(engine)
    if 'companies' in inspector.get_table_names():
        _add_columns(engine, 'companies', {
            'industry': 'VARCHAR(100)',
            'main_business': 'TEXT',
        })
    if 'business_lines' in inspector.get_table_names():
        _add_columns(engine, 'business_lines', {
            'confidence': 'VARCHAR(20)',
            'generated_by': 'VARCHAR(20)',
        })
    if 'business_line_evidence' in inspector.get_table_names():
        _add_columns(engine, 'business_line_evidence', {
            'hypothesis_id': 'INTEGER',
            'risk_event_id': 'INTEGER',
            'source_name': 'VARCHAR(100)',
            'source_title': 'VARCHAR(255)',
            'source_url': 'VARCHAR(500)',
            'source_date': 'TIMESTAMP',
            'severity': 'VARCHAR(20) DEFAULT \'low\'',
            'review_status': 'VARCHAR(20) DEFAULT \'pending\'',
            'ai_summary': 'TEXT',
            'ai_impact_judgment': 'VARCHAR(20)',
            'ai_reason': 'TEXT',
            'ai_confidence': 'VARCHAR(20)',
            'ai_generated_at': 'TIMESTAMP',
            'manual_override': 'BOOLEAN DEFAULT FALSE',
            'manual_note': 'TEXT',
            'reviewed_at': 'TIMESTAMP',
            'reviewer': 'VARCHAR(100)',
            'review_note': 'TEXT',
            'original_content': 'TEXT',
            'edited_content': 'TEXT',
            'hypothesis_relation': 'VARCHAR(20) DEFAULT \'watch\'',
            'impact_strength': 'VARCHAR(20) DEFAULT \'low\'',
            'affected_aspect': 'VARCHAR(50) DEFAULT \'other\'',
            'evidence_summary': 'TEXT',
            'relation_note': 'TEXT',
            'ingestion_run_id': 'INTEGER',
            'raw_payload': 'JSON',
            'content_hash': 'VARCHAR(64)',
        })
    if 'announcements' in inspector.get_table_names():
        _add_columns(engine, 'announcements', {
            'source_name': 'VARCHAR(100)',
            'ingestion_run_id': 'INTEGER',
            'raw_payload': 'JSON',
        })
    if 'news_items' in inspector.get_table_names():
        _add_columns(engine, 'news_items', {
            'source_name': 'VARCHAR(100)',
            'ingestion_run_id': 'INTEGER',
            'raw_payload': 'JSON',
        })
    if 'financial_snapshots' in inspector.get_table_names():
        _add_columns(engine, 'financial_snapshots', {
            'source_name': 'VARCHAR(100)',
            'ingestion_run_id': 'INTEGER',
        })
    if 'investment_hypotheses' in inspector.get_table_names():
        _add_columns(engine, 'investment_hypotheses', {
            'thesis': 'TEXT',
            'business_lines': 'JSON',
            'watch_metrics': 'JSON',
            'positive_evidence_rules': 'JSON',
            'negative_evidence_rules': 'JSON',
            'invalidation_conditions': 'JSON',
            'current_view': 'VARCHAR(20) DEFAULT \'neutral\'',
            'tracking_priority': 'VARCHAR(20) DEFAULT \'medium\'',
            'note': 'TEXT',
        })
    if 'ingestion_runs' not in inspector.get_table_names():
        with engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE ingestion_runs (
                    id INTEGER PRIMARY KEY,
                    company_id INTEGER,
                    source_name VARCHAR(100) NOT NULL,
                    source_type VARCHAR(50) NOT NULL,
                    status VARCHAR(20) DEFAULT 'success',
                    started_at TIMESTAMP,
                    finished_at TIMESTAMP,
                    duration_ms INTEGER,
                    items_found INTEGER DEFAULT 0,
                    items_created INTEGER DEFAULT 0,
                    items_updated INTEGER DEFAULT 0,
                    error_message TEXT,
                    raw_error TEXT,
                    request_params JSON,
                    result_summary JSON,
                    created_at TIMESTAMP,
                    updated_at TIMESTAMP
                )
            """))
    if 'research_notes' not in inspector.get_table_names():
        with engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE research_notes (
                    id INTEGER PRIMARY KEY,
                    company_id INTEGER NOT NULL,
                    hypothesis_id INTEGER,
                    title VARCHAR(255) NOT NULL,
                    note_type VARCHAR(50) DEFAULT 'manual_note',
                    conclusion_direction VARCHAR(20) DEFAULT 'watch',
                    summary TEXT,
                    content TEXT,
                    cited_evidence_ids JSON,
                    evidence_count INTEGER DEFAULT 0,
                    reviewed_evidence_count INTEGER DEFAULT 0,
                    unreviewed_evidence_count INTEGER DEFAULT 0,
                    status VARCHAR(20) DEFAULT 'active',
                    created_at TIMESTAMP,
                    updated_at TIMESTAMP
                )
            """))
    if 'discipline_checks' not in inspector.get_table_names():
        with engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE discipline_checks (
                    id INTEGER PRIMARY KEY,
                    company_id INTEGER NOT NULL,
                    hypothesis_id INTEGER,
                    title VARCHAR(255) NOT NULL,
                    status VARCHAR(20) DEFAULT 'draft',
                    discipline_result VARCHAR(20) DEFAULT 'blocked',
                    thesis_snapshot TEXT,
                    action_reason TEXT,
                    position_plan TEXT,
                    max_position_pct FLOAT,
                    risk_acknowledgement TEXT,
                    invalidation_plan TEXT,
                    checklist JSON,
                    cited_evidence_ids JSON,
                    cited_research_note_ids JSON,
                    evidence_count INTEGER DEFAULT 0,
                    reviewed_evidence_count INTEGER DEFAULT 0,
                    unreviewed_evidence_count INTEGER DEFAULT 0,
                    rejected_evidence_count INTEGER DEFAULT 0,
                    blockers JSON,
                    completed_at TIMESTAMP,
                    created_at TIMESTAMP,
                    updated_at TIMESTAMP
                )
            """))


def _add_columns(engine, table_name: str, columns: dict[str, str]):
    inspector = inspect(engine)
    existing = {column['name'] for column in inspector.get_columns(table_name)}
    with engine.begin() as conn:
        for name, ddl_type in columns.items():
            if name not in existing:
                conn.execute(text(f'ALTER TABLE {table_name} ADD COLUMN {name} {ddl_type}'))
