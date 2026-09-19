"""Klien TikTok Shop (Tokopedia) read-only: tanda tangan HMAC-SHA256 + pencarian pesanan. Testable tanpa LLM."""

import hashlib
import hmac
import json
import time

from core import config
from core.http import ApiError, request
from tokopedia import auth

_cache: dict[str, str] = {}
_PAGE_SIZE = 100


def sign(path: str, params: dict, body: str, secret: str) -> str:
    """Path + {key}{value} terurut (tanpa sign/access_token) + body, dibungkus secret, HMAC-SHA256."""
    keys = sorted(k for k in params if k not in ("sign", "access_token"))
    s = path + "".join(f"{k}{params[k]}" for k in keys) + body
    return hmac.new(secret.encode(), (secret + s + secret).encode(), hashlib.sha256).hexdigest()


def call(method: str, path: str, params: dict | None = None, body: dict | None = None, shop: bool = True) -> dict:
    if not (config.TTS_APP_KEY and config.TTS_APP_SECRET):
        raise ApiError("TTS_APP_KEY / TTS_APP_SECRET belum diisi (cek .env).")
    p = {"app_key": config.TTS_APP_KEY, "timestamp": str(int(time.time())), **(params or {})}
    if shop:
        p["shop_cipher"] = shop_cipher()
    raw = json.dumps(body, separators=(",", ":")) if body is not None else ""
    p["sign"] = sign(path, p, raw, config.TTS_APP_SECRET)
    resp = request(
        method, f"{config.TTS_API_URL}{path}", require_base=config.TTS_API_URL, params=p, data=raw or None,
        headers={"x-tts-access-token": auth.get_access_token(), "content-type": "application/json"},
    )
    out = resp.json()
    if out.get("code") not in (0, None):  # TikTok membalas HTTP 200 walau gagal
        raise ApiError(f"{path}: code={out.get('code')} {out.get('message')}")
    return out.get("data") or {}


def shop_cipher() -> str:
    if config.TTS_SHOP_CIPHER:
        return config.TTS_SHOP_CIPHER
    if "cipher" not in _cache:
        shops = call("GET", "/authorization/202309/shops", shop=False).get("shops", [])
        if len(shops) != 1:
            names = ", ".join(f"{s.get('name')}={s.get('cipher')}" for s in shops)
            raise ApiError(f"Ditemukan {len(shops)} toko; isi TTS_SHOP_CIPHER. Toko: {names}")
        _cache["cipher"] = shops[0]["cipher"]
    return _cache["cipher"]


def brief(o: dict) -> dict:
    """Hanya field operasional. Data pembeli (nama, alamat, telepon, email) SENGAJA dibuang."""
    pay = o.get("payment") or {}
    return {
        "id": str(o.get("id")), "status": o.get("status"),
        "create_time": int(o.get("create_time") or 0), "update_time": int(o.get("update_time") or 0),
        "total_amount": pay.get("total_amount"), "currency": pay.get("currency"),
        "items": len(o.get("line_items") or []),
    }


def search_orders(body: dict, max_pages: int = 10) -> tuple[list[dict], bool]:
    """Return (pesanan ringkas, terpotong?). Terpotong jika masih ada halaman setelah max_pages."""
    out: list[dict] = []
    token = None
    for _ in range(max_pages):
        params = {"page_size": _PAGE_SIZE, "sort_field": "create_time", "sort_order": "DESC"}
        if token:
            params["page_token"] = token
        data = call("POST", "/order/202309/orders/search", params=params, body=body)
        out += [brief(o) for o in data.get("orders", [])]
        token = data.get("next_page_token")
        if not token:
            return out, False
    return out, True


def fetch_order_snapshot(days: int = 7, progress=None) -> dict:
    since = int(time.time()) - days * 86400
    if progress:
        progress("mengambil pesanan...")
    recent, trunc = search_orders({"create_time_ge": since})
    if progress:
        progress(f"{len(recent)} pesanan; mengecek permintaan pembatalan pembeli...")
    cancel, trunc2 = search_orders({"create_time_ge": since, "is_buyer_request_cancel": True})
    return {"days": days, "orders": recent, "cancel_requests": cancel, "truncated": trunc or trunc2}
