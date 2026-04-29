import hashlib
from datetime import datetime


def content_hash(*parts) -> str:
    text = '|'.join(str(part or '') for part in parts)
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def serialize_dt(value):
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def importance_score(is_risk: bool, is_business_update: bool, default: int = 3) -> int:
    if is_risk:
        return 5
    if is_business_update:
        return 4
    return default
