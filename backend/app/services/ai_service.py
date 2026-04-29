from app.ai.base import AIProvider


class AIService:
    def __init__(self, provider: AIProvider):
        self.provider = provider

    def analyze_logic_impact(self, payload: dict) -> dict:
        return self.provider.analyze_logic_impact(payload)
