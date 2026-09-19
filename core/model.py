"""Bikin model sekali, dipakai semua agent. Provider dipilih lewat LLM_PROVIDER (ollama | openrouter)."""

from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.providers.openrouter import OpenRouterProvider

from core import config


def get_model(model_name: str | None = None, provider: str | None = None) -> OpenAIChatModel:
    provider = (provider or config.LLM_PROVIDER).lower()
    if provider == "ollama":
        # Ollama abaikan api_key, isi apa saja.
        return OpenAIChatModel(
            model_name or config.OLLAMA_MODEL,
            provider=OpenAIProvider(base_url=config.OLLAMA_URL, api_key="ollama"),
        )
    if provider == "openrouter":
        name = model_name or config.OPENROUTER_MODEL
        if not config.OPENROUTER_API_KEY:
            raise ValueError("OPENROUTER_API_KEY belum diisi (cek .env).")
        if not name:
            raise ValueError("Model OpenRouter belum dipilih: isi OPENROUTER_MODEL, contoh 'qwen/qwen-2.5-72b-instruct'.")
        return OpenAIChatModel(name, provider=OpenRouterProvider(api_key=config.OPENROUTER_API_KEY))
    raise ValueError(f"LLM_PROVIDER tidak dikenal: {provider!r} (pilih 'ollama' atau 'openrouter').")
