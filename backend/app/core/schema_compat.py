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
        })


def _add_columns(engine, table_name: str, columns: dict[str, str]):
    inspector = inspect(engine)
    existing = {column['name'] for column in inspector.get_columns(table_name)}
    with engine.begin() as conn:
        for name, ddl_type in columns.items():
            if name not in existing:
                conn.execute(text(f'ALTER TABLE {table_name} ADD COLUMN {name} {ddl_type}'))
