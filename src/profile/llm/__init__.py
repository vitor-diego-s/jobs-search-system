"""LLM provider registry with lazy loading.

Usage:
    from src.profile.llm import get_provider, parse_response

    provider = get_provider("anthropic")
    raw = provider.complete(resume_text)
    profile = parse_response(raw)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.profile.llm.base import LLMProvider, parse_response

if TYPE_CHECKING:
    pass

__all__ = ["LLMProvider", "available_providers", "get_provider", "parse_response"]

# Lazy registry: maps provider name → (module_path, class_name)
_REGISTRY: dict[str, tuple[str, str]] = {
    "anthropic": ("src.profile.llm.anthropic", "AnthropicProvider"),
    "openai": ("src.profile.llm.openai", "OpenAIProvider"),
    "gemini": ("src.profile.llm.gemini", "GeminiProvider"),
    "ollama": ("src.profile.llm.ollama", "OllamaProvider"),
}


def get_provider(name: str) -> LLMProvider:
    """Instantiate and return an LLM provider by name.

    Args:
        name: Provider identifier (anthropic, openai, gemini, ollama).

    Returns:
        An LLMProvider instance.

    Raises:
        ValueError: If the provider name is unknown.
    """
    if name not in _REGISTRY:
        valid = ", ".join(sorted(_REGISTRY))
        msg = f"Unknown LLM provider '{name}'. Available: {valid}"
        raise ValueError(msg)

    module_path, class_name = _REGISTRY[name]

    import importlib

    module = importlib.import_module(module_path)
    cls = getattr(module, class_name)
    return cls()  # type: ignore[no-any-return]


def available_providers() -> list[str]:
    """Return sorted list of registered provider names."""
    return sorted(_REGISTRY)
