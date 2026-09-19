"""Klasifikasi pesanan bermasalah secara deterministik -- tanpa LLM."""

import time
from collections import Counter

from tokopedia.schemas import OrderIssue, OrderReport

_CLOSED = {"CANCELLED", "COMPLETED", "DELIVERED"}


def build_order_report(snapshot: dict, overdue_hours: float = 24, now: float | None = None) -> OrderReport:
    now = now or time.time()
    orders = snapshot["orders"]
    counts = dict(Counter(o["status"] or "UNKNOWN" for o in orders))
    issues: list[OrderIssue] = []

    for o in orders:
        age = (now - o["create_time"]) / 3600
        if o["status"] == "AWAITING_SHIPMENT" and age > overdue_hours:
            issues.append(OrderIssue(
                order_id=o["id"], kind="overdue_shipment", status=o["status"], age_hours=round(age, 1),
                detail=f"Belum dikirim {age:.0f} jam sejak dibuat (batas {overdue_hours:g} jam)."))
    seen = set()
    for o in snapshot["cancel_requests"]:
        if o["status"] in _CLOSED or o["id"] in seen:
            continue
        seen.add(o["id"])
        age = (now - o["create_time"]) / 3600
        issues.append(OrderIssue(
            order_id=o["id"], kind="buyer_cancel_request", status=o["status"], age_hours=round(age, 1),
            detail="Pembeli meminta pembatalan; perlu ditanggapi penjual."))

    issues.sort(key=lambda i: (i.kind != "buyer_cancel_request", -i.age_hours))
    n_over = sum(1 for i in issues if i.kind == "overdue_shipment")
    n_cancel = len(issues) - n_over
    summary = (f"{len(orders)} pesanan dalam {snapshot['days']} hari: {counts.get('AWAITING_SHIPMENT', 0)} menunggu kirim "
               f"({n_over} terlambat), {n_cancel} permintaan batal pembeli.")
    if snapshot["truncated"]:
        summary += " (data terpotong: terlalu banyak pesanan)"
    return OrderReport(summary=summary, window_days=snapshot["days"], total_orders=len(orders),
                       status_counts=counts, issues=issues, truncated=snapshot["truncated"])
