"""Helper HTTP bersama: error HTTP/jaringan jadi ApiError, bukan JSON error yang diam-diam lolos."""

import functools
from typing import Any

import requests


class ApiError(Exception):
    pass


def request(method: str, url: str, *, require_base: str = "", **kwargs: Any) -> requests.Response:
    if not require_base:
        raise ApiError("Base URL belum dikonfigurasi (cek env var / .env).")
    kwargs.setdefault("timeout", 30)
    try:
        resp = requests.request(method, url, **kwargs)
    except requests.RequestException as e:
        raise ApiError(f"Gagal menghubungi {url}: {e}") from e
    if resp.status_code >= 400:
        raise ApiError(f"{method} {url} -> HTTP {resp.status_code}: {resp.text[:300]}")
    return resp


def tool_errors(fn):
    """Untuk wrapper tool agent: ApiError dikembalikan sebagai teks supaya LLM bisa melaporkannya."""

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except ApiError as e:
            return f"ERROR: {e}"

    return wrapper
