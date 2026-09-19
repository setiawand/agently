"""Konfigurasi bersama untuk semua agent -- diisi dari env var / .env, sekali tempat."""

import os

from dotenv import load_dotenv

load_dotenv()

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434/v1")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:32b")

# CI/CD agent (GitLab)
GITLAB_URL = os.environ.get("GITLAB_URL", "").rstrip("/")
GITLAB_TOKEN = os.environ.get("GITLAB_TOKEN", "")

# n8n agent
N8N_URL = os.environ.get("N8N_URL", "").rstrip("/")
N8N_API_KEY = os.environ.get("N8N_API_KEY", "")

# Pemilihan LLM: "ollama" (default, lokal/on-prem) atau "openrouter" (cloud pihak ketiga)
# "off" -> kirim reasoning_effort=none (matikan thinking; jauh lebih cepat di model lokal seperti qwen3.5)
LLM_THINKING = os.environ.get("LLM_THINKING", "").lower()
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "ollama").lower()
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "")

# Trace aktivitas model ke stderr (lokal, tanpa layanan luar)
TRACE = os.environ.get("AGENTLY_TRACE", "").lower() in ("1", "true", "yes")

# Tokopedia (TikTok Shop Partner API, custom app untuk toko sendiri)
TTS_API_URL = os.environ.get("TTS_API_URL", "https://open-api.tiktokglobalshop.com").rstrip("/")
TTS_AUTH_URL = os.environ.get("TTS_AUTH_URL", "https://auth.tiktok-shops.com").rstrip("/")
TTS_APP_KEY = os.environ.get("TTS_APP_KEY", "")
TTS_APP_SECRET = os.environ.get("TTS_APP_SECRET", "")
TTS_ACCESS_TOKEN = os.environ.get("TTS_ACCESS_TOKEN", "")
TTS_REFRESH_TOKEN = os.environ.get("TTS_REFRESH_TOKEN", "")
TTS_SHOP_CIPHER = os.environ.get("TTS_SHOP_CIPHER", "")
TTS_TOKEN_FILE = os.environ.get("TTS_TOKEN_FILE", ".tts_tokens.json")
