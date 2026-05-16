"""Provider factory selection logic."""

from __future__ import annotations

from src.ai.providers import get_provider
from src.ai.providers.echo import EchoProvider
from src.ai.providers.groq import GroqProvider


def test_force_echo_returns_echo():
    assert isinstance(get_provider(force="echo"), EchoProvider)


def test_force_groq_with_no_key_falls_back_to_echo(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    assert isinstance(get_provider(force="groq"), EchoProvider)


def test_force_groq_with_key_returns_groq(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "fake-key-for-test")
    prov = get_provider(force="groq")
    assert isinstance(prov, GroqProvider)
    assert prov.info.name == "groq"


def test_unknown_provider_falls_back_to_echo():
    assert isinstance(get_provider(force="mystery"), EchoProvider)
