from abc import ABC, abstractmethod


class AIProvider(ABC):
    @abstractmethod
    def analyze_logic_impact(self, payload: dict) -> dict: ...
