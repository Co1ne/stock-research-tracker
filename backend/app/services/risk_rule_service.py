RISK_KEYWORDS = ['减持', '资产减值', '计提减值', '诉讼', '仲裁', '担保', '违规', '处罚', '问询函', '立案', '业绩下降', '亏损']


def detect_risk(text: str) -> tuple[bool, str]:
    hit = [k for k in RISK_KEYWORDS if k in text]
    if not hit:
        return False, 'low'
    if len(hit) >= 3:
        return True, 'high'
    if len(hit) == 2:
        return True, 'medium'
    return True, 'low'
