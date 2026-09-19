"""Token TikTok Shop: access token (7 hari) di-refresh otomatis; refresh token BERPUTAR, jadi wajib disimpan.

Token disimpan di TTS_TOKEN_FILE (chmod 600, di-gitignore). Isi file menimpa nilai dari env.
Bootstrap pertama: python -m tokopedia.auth <auth_code>
"""

import json
import os
import sys
import time

from core import config
from core.http import ApiError, request

_REFRESH_MARGIN = 24 * 3600


def _load() -> dict:
    tokens = {"access_token": config.TTS_ACCESS_TOKEN, "refresh_token": config.TTS_REFRESH_TOKEN}
    try:
        with open(config.TTS_TOKEN_FILE) as f:
            tokens.update(json.load(f))
    except FileNotFoundError:
        pass
    return tokens


def _save(tokens: dict) -> None:
    fd = os.open(config.TTS_TOKEN_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(tokens, f)
    os.chmod(config.TTS_TOKEN_FILE, 0o600)


def _token_call(path: str, params: dict) -> dict:
    if not (config.TTS_APP_KEY and config.TTS_APP_SECRET):
        raise ApiError("TTS_APP_KEY / TTS_APP_SECRET belum diisi (cek .env).")
    body = request("GET", f"{config.TTS_AUTH_URL}{path}", require_base=config.TTS_AUTH_URL,
                   params={"app_key": config.TTS_APP_KEY, "app_secret": config.TTS_APP_SECRET, **params}).json()
    if body.get("code") not in (0, None):
        raise ApiError(f"Token API gagal: code={body.get('code')} {body.get('message')}")
    data = body.get("data") or {}
    if not data.get("access_token"):
        raise ApiError("Token API tidak mengembalikan access_token.")
    tokens = {k: data[k] for k in ("access_token", "access_token_expire_in", "refresh_token", "refresh_token_expire_in")
              if k in data}
    _save(tokens)
    return tokens


def exchange_code(auth_code: str) -> dict:
    return _token_call("/api/v2/token/get", {"auth_code": auth_code, "grant_type": "authorized_code"})


def refresh(refresh_token: str) -> dict:
    return _token_call("/api/v2/token/refresh", {"refresh_token": refresh_token, "grant_type": "refresh_token"})


def get_access_token() -> str:
    t = _load()
    if not t.get("access_token") and not t.get("refresh_token"):
        raise ApiError("Belum ada token. Jalankan: python -m tokopedia.auth <auth_code>")
    expire = t.get("access_token_expire_in")
    needs_refresh = not t.get("access_token") or (
        t.get("refresh_token") and (expire is None or expire - time.time() < _REFRESH_MARGIN))
    if needs_refresh:
        t = refresh(t["refresh_token"])
    return t["access_token"]


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Pemakaian: python -m tokopedia.auth <auth_code>")
    exchange_code(sys.argv[1])
    print(f"Token tersimpan di {config.TTS_TOKEN_FILE}")
