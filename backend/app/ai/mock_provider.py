from app.ai.base import AIProvider


class MockAIProvider(AIProvider):
    def analyze_logic_impact(self, payload: dict) -> dict:
        text = f"{payload['item'].get('title', '')} {payload['item'].get('raw_text', '')}"
        if any(k in text for k in ['中标', '订单', '合同', '增长']):
            return {'logic_impact': 'strengthen', 'evidence_type': 'order', 'related_business_line_ids': [], 'confidence': 'high', 'reason': '订单/增长信号', 'need_manual_review': False}
        if any(k in text for k in ['减持', '诉讼', '亏损']):
            return {'logic_impact': 'weaken', 'evidence_type': 'risk', 'related_business_line_ids': [], 'confidence': 'medium', 'reason': '风险关键词', 'need_manual_review': True}
        return {'logic_impact': 'neutral', 'evidence_type': 'other', 'related_business_line_ids': [], 'confidence': 'low', 'reason': '无明显信号', 'need_manual_review': False}
