# sql_coach/ai/factory.py
"""AI engine factory."""
from ..models import Config
from .base import AIEngine


def create_ai_engine(model: str, config: Config) -> AIEngine:
    """Create an AI engine based on model name.

    In mock mode, returns MockAIEngine to avoid real API calls.
    """
    if config.mock:
        from .mock import MockAIEngine
        return MockAIEngine()

    if model == "deepseek":
        from .deepseek import DeepSeekEngine
        return DeepSeekEngine(api_key=config.deepseek_api_key)
    elif model == "openai":
        from .openai_adapter import OpenAIEngine
        return OpenAIEngine(api_key=config.openai_api_key)
    elif model == "ollama":
        from .ollama import OllamaEngine
        return OllamaEngine(url=config.ollama_url)
    raise ValueError(f"Unknown AI model: {model}")
