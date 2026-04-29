from app.ai.base import AIProvider


class OpenAIProvider(AIProvider):
    def analyze_logic_impact(self, payload: dict) -> dict:
        raise NotImplementedError('V2预留，不做真实调用')
