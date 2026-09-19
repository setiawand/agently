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
