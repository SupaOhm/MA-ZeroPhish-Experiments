"""Provider name -> client. The two providers the experiments use."""

from .gemini import GeminiClient
from .openrouter import OpenRouterClient

PROVIDERS = {"gemini": GeminiClient, "openrouter": OpenRouterClient}


def make_client(provider: str, model: str, **kw):
    if provider not in PROVIDERS:
        raise ValueError(f"unknown provider: {provider!r} (use one of {sorted(PROVIDERS)})")
    return PROVIDERS[provider](model, **kw)
