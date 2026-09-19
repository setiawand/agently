import hashlib
import hmac
import json
import time

import pytest

from core import config
from core.http import ApiError
from tokopedia import auth, main, report, tools


class R:
    def __init__(self, data, status=200):
        self._d, self.status_code, self.text = data, status, json.dumps(data)

    def json(self):
        return self._d


@pytest.fixture(autouse=True)
def cfg(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "TTS_APP_KEY", "key")
    monkeypatch.setattr(config, "TTS_APP_SECRET", "sec")
    monkeypatch.setattr(config, "TTS_SHOP_CIPHER", "CIPHER")
    monkeypatch.setattr(config, "TTS_ACCESS_TOKEN", "")
    monkeypatch.setattr(config, "TTS_REFRESH_TOKEN", "")
    monkeypatch.setattr(config, "TTS_TOKEN_FILE", str(tmp_path / "tok.json"))
    tools._cache.clear()


def test_sign_matches_documented_algorithm():
    params = {"timestamp": "1", "app_key": "k", "sign": "x", "access_token": "t", "shop_cipher": "c"}
    expected_str = "sec" + "/order/202309/orders/search" + "app_keyk" + "shop_cipherc" + "timestamp1" + '{"a":1}' + "sec"
    expected = hmac.new(b"sec", expected_str.encode(), hashlib.sha256).hexdigest()
    assert tools.sign("/order/202309/orders/search", params, '{"a":1}', "sec") == expected


def test_call_signs_sends_token_and_checks_code(monkeypatch):
    auth._save({"access_token": "AT", "refresh_token": "RT", "access_token_expire_in": time.time() + 10 * 86400})
    seen = {}

    def fake(method, url, **kw):
        seen.update(kw, url=url, method=method)
        return R({"code": 0, "data": {"ok": 1}})

    monkeypatch.setattr("requests.request", fake)
    assert tools.call("POST", "/order/202309/orders/search", body={"a": 1}) == {"ok": 1}
    assert seen["headers"]["x-tts-access-token"] == "AT"
    p = seen["params"]
    assert p["sign"] == tools.sign("/order/202309/orders/search", p, '{"a":1}', "sec") and seen["data"] == '{"a":1}'

    monkeypatch.setattr("requests.request", lambda *a, **k: R({"code": 105001, "message": "bad token"}))
    with pytest.raises(ApiError, match="105001"):
        tools.call("POST", "/order/202309/orders/search", body={})


def test_token_refresh_persists_rotated_refresh_token(monkeypatch):
    auth._save({"access_token": "old", "refresh_token": "R1", "access_token_expire_in": time.time() + 60})
    calls = []

    def fake(method, url, **kw):
        calls.append(kw["params"])
        return R({"code": 0, "data": {"access_token": "new", "refresh_token": "R2",
                                       "access_token_expire_in": time.time() + 7 * 86400}})

    monkeypatch.setattr("requests.request", fake)
    assert auth.get_access_token() == "new"
    assert calls[0]["refresh_token"] == "R1" and auth._load()["refresh_token"] == "R2"
    assert auth.get_access_token() == "new" and len(calls) == 1  # masih segar -> tidak refresh lagi
    import os, stat
    assert stat.S_IMODE(os.stat(config.TTS_TOKEN_FILE).st_mode) == 0o600


def test_no_token_error():
    with pytest.raises(ApiError, match="tokopedia.auth"):
        auth.get_access_token()


def test_single_shop_cipher_autodetect_and_multi_error(monkeypatch):
    monkeypatch.setattr(config, "TTS_SHOP_CIPHER", "")
    monkeypatch.setattr(tools, "call", lambda *a, **k: {"shops": [{"name": "A", "cipher": "C1"}]})
    assert tools.shop_cipher() == "C1"
    tools._cache.clear()
    monkeypatch.setattr(tools, "call", lambda *a, **k: {"shops": [{"name": "A", "cipher": "C1"}, {"name": "B", "cipher": "C2"}]})
    with pytest.raises(ApiError, match="TTS_SHOP_CIPHER"):
        tools.shop_cipher()


def test_brief_drops_pii():
    b = tools.brief({"id": 1, "status": "X", "create_time": 5, "buyer_email": "a@b.c",
                     "recipient_address": {"name": "Budi", "phone_number": "08"}, "payment": {"total_amount": "10", "currency": "IDR"},
                     "line_items": [1, 2]})
    assert "Budi" not in json.dumps(b) and "a@b.c" not in json.dumps(b) and b["items"] == 2


def test_search_orders_paginates_and_flags_truncation(monkeypatch):
    pages = iter([{"orders": [{"id": 1}], "next_page_token": "n"}, {"orders": [{"id": 2}], "next_page_token": ""}])
    monkeypatch.setattr(tools, "call", lambda *a, **k: next(pages))
    out, trunc = tools.search_orders({})
    assert [o["id"] for o in out] == ["1", "2"] and not trunc

    monkeypatch.setattr(tools, "call", lambda *a, **k: {"orders": [{"id": 9}], "next_page_token": "more"})
    _, trunc = tools.search_orders({}, max_pages=2)
    assert trunc


def test_report_classification():
    now = 1_000_000.0
    h = 3600
    snap = {"days": 7, "truncated": False, "orders": [
        {"id": "1", "status": "AWAITING_SHIPMENT", "create_time": now - 30 * h},   # terlambat
        {"id": "2", "status": "AWAITING_SHIPMENT", "create_time": now - 2 * h},    # masih aman
        {"id": "3", "status": "COMPLETED", "create_time": now - 50 * h},
    ], "cancel_requests": [
        {"id": "4", "status": "AWAITING_SHIPMENT", "create_time": now - 5 * h},
        {"id": "3", "status": "COMPLETED", "create_time": now - 50 * h},           # sudah tertutup
    ]}
    r = report.build_order_report(snap, overdue_hours=24, now=now)
    assert [(i.order_id, i.kind) for i in r.issues] == [("4", "buyer_cancel_request"), ("1", "overdue_shipment")]
    assert r.status_counts == {"AWAITING_SHIPMENT": 2, "COMPLETED": 1}
    assert "2 menunggu kirim (1 terlambat)" in r.summary


def test_summarize_llm_and_fallback(monkeypatch):
    from pydantic_ai.models.test import TestModel

    snap = {"days": 7, "truncated": False, "orders": [], "cancel_requests": []}
    monkeypatch.setattr(tools, "fetch_order_snapshot", lambda d, p=None: snap)
    monkeypatch.setattr(main, "get_model", lambda n=None: TestModel(custom_output_text="Aman."))
    assert main.summarize_orders() == "Aman."

    class Boom:
        def __getattr__(self, n): raise RuntimeError("down")
    monkeypatch.setattr(main, "get_model", lambda n=None: Boom())
    assert "0 pesanan" in main.summarize_orders()
