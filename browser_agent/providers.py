"""Select a configured model backend without changing browser or agent code."""

from .codex_provider import CodexProvider
from .config import Settings
from .llm import DecisionProvider, OpenAIProvider
from .ollama_provider import OllamaProvider


def create_provider(settings: Settings) -> DecisionProvider:
    if settings.llm_provider == "codex":
        return CodexProvider(settings)
    if settings.llm_provider == "ollama":
        return OllamaProvider(settings)
    return OpenAIProvider(settings)
