"""Provider factory.

Order of preference, settable via `RAMPART_AI_PROVIDER`:
  - 'groq'  : real LLM via Groq (requires GROQ_API_KEY)
  - 'echo'  : deterministic, no key, used by tests + offline demos

If RAMPART_AI_PROVIDER is unset, we pick groq when GROQ_API_KEY is
present, otherwise echo. Tests that need a forced provider should
either set the env var or call `get_provider(force='echo')`.
"""

from __future__ import annotations

import logging
import os

from src.ai.providers.base import Provider, ProviderError, ProviderInfo
from src.ai.providers.echo import EchoProvider
from src.ai.providers.groq import GroqProvider

_log = logging.getLogger(__name__)


def get_provider(force: str | None = None) -> Provider:
    choice = (force or os.environ.get("RAMPART_AI_PROVIDER") or "").strip().lower()
    if not choice:
        choice = "groq" if os.environ.get("GROQ_API_KEY") else "echo"

    if choice == "groq":
        key = os.environ.get("GROQ_API_KEY")
        if not key:
            _log.warning("GROQ_API_KEY missing; falling back to echo provider")
            return EchoProvider()
        return GroqProvider(api_key=key)
    if choice == "echo":
        return EchoProvider()

    _log.warning("unknown RAMPART_AI_PROVIDER=%r; falling back to echo", choice)
    return EchoProvider()


__all__ = ["Provider", "ProviderError", "ProviderInfo", "get_provider"]
