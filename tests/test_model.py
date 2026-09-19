import pytest

from core import config
from core.model import get_model


def test_default_is_ollama(monkeypatch):
    monkeypatch.setattr(config, "LLM_PROVIDER", "ollama")
    m = get_model("foo")
    assert m.model_name == "foo" and "11434" in str(m.client.base_url)


def test_openrouter(monkeypatch):
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "k")
    monkeypatch.setattr(config, "OPENROUTER_MODEL", "qwen/x")
    m = get_model(provider="openrouter")
    assert m.model_name == "qwen/x" and "openrouter.ai" in str(m.client.base_url)


def test_openrouter_requires_key_and_model(monkeypatch):
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "")
    with pytest.raises(ValueError, match="API_KEY"):
        get_model("x", provider="openrouter")
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "k")
    monkeypatch.setattr(config, "OPENROUTER_MODEL", "")
    with pytest.raises(ValueError, match="OPENROUTER_MODEL"):
        get_model(provider="openrouter")


def test_unknown_provider():
    with pytest.raises(ValueError):
        get_model(provider="nope")
