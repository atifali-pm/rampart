"""Groq provider.

Uses the OpenAI-compatible Chat Completions endpoint at api.groq.com.
Requires `GROQ_API_KEY` in the environment. The default model is
`llama-3.3-70b-versatile`, which is on Groq's free tier at the time
of writing; override with `GROQ_MODEL=...` to switch.

Failures fall through as `ProviderError`. Callers should catch and
decide whether to retry, surface a user-facing message, or fall back
to the EchoProvider.
"""

from __future__ import annotations

import json
import os
from typing import Any

import httpx

from src.ai.providers.base import Provider, ProviderError, ProviderInfo

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_MODEL = "llama-3.3-70b-versatile"
DEFAULT_TIMEOUT_SECONDS = 30.0


class GroqProvider(Provider):
    def __init__(
        self,
        *,
        api_key: str,
        model: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._api_key = api_key
        self._model = model or os.environ.get("GROQ_MODEL", DEFAULT_MODEL)
        self._timeout = timeout

    @property
    def info(self) -> ProviderInfo:
        return ProviderInfo(name="groq", model=self._model)

    def _call(self, payload: dict[str, Any]) -> str:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        try:
            r = httpx.post(GROQ_URL, headers=headers, json=payload, timeout=self._timeout)
        except httpx.HTTPError as exc:
            raise ProviderError(f"groq HTTP error: {exc}") from exc
        if r.status_code >= 400:
            raise ProviderError(f"groq {r.status_code}: {r.text[:400]}")
        try:
            body = r.json()
            return body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, ValueError) as exc:
            raise ProviderError(f"groq malformed response: {exc}") from exc

    def generate_text(self, *, system: str, user: str) -> str:
        return self._call(
            {
                "model": self._model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": 0.3,
            }
        )

    def generate_json(
        self,
        *,
        system: str,
        user: str,
        schema: dict[str, Any],
    ) -> dict[str, Any]:
        schema_hint = json.dumps(schema, indent=2)
        sys_with_schema = (
            f"{system}\n\n"
            "Respond with ONLY a single JSON object that matches this JSON Schema. "
            "Do not wrap in code fences. Do not add commentary.\n\n"
            f"Schema:\n{schema_hint}"
        )
        content = self._call(
            {
                "model": self._model,
                "messages": [
                    {"role": "system", "content": sys_with_schema},
                    {"role": "user", "content": user},
                ],
                "temperature": 0.2,
                "response_format": {"type": "json_object"},
            }
        )
        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            raise ProviderError(f"groq returned non-JSON content: {exc}") from exc
