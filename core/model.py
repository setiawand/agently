"""Bikin OpenAIChatModel yang mengarah ke Ollama sekali, dipakai semua agent."""

from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from core.config import OLLAMA_URL, OLLAMA_MODEL


def get_ollama_model(model_name: str | None = None) -> OpenAIChatModel:
    """Model Ollama via endpoint OpenAI-compatible. Ollama abaikan api_key, isi apa saja."""
    return OpenAIChatModel(
        model_name or OLLAMA_MODEL,
        provider=OpenAIProvider(base_url=OLLAMA_URL, api_key="ollama"),
    )
