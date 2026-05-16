"""LLM provider abstraction.

The deterministic core never imports anything from this module. Agents
that produce *recommendations* import a Provider via `get_provider()`.
This lets us swap Groq for OpenRouter, Gemini, Claude, or a local
Ollama call without touching agent code.

Every call returns a Python dict that conforms to the JSON schema the
caller passes in. Providers are expected to enforce the schema however
they can (structured output mode, retry-with-correction, or a hand
parser); the agent treats the return value as already-validated.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ProviderInfo:
    name: str
    model: str


class ProviderError(RuntimeError):
    """Raised when the provider cannot return a usable response."""


class Provider(ABC):
    @property
    @abstractmethod
    def info(self) -> ProviderInfo: ...

    @abstractmethod
    def generate_json(
        self,
        *,
        system: str,
        user: str,
        schema: dict[str, Any],
    ) -> dict[str, Any]: ...

    @abstractmethod
    def generate_text(self, *, system: str, user: str) -> str: ...
