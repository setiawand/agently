from typing import Literal

from pydantic import BaseModel, Field


class OrderIssue(BaseModel):
    order_id: str
    kind: Literal["overdue_shipment", "buyer_cancel_request"]
    status: str | None = None
    age_hours: float
    detail: str


class OrderReport(BaseModel):
    summary: str
    window_days: int
    total_orders: int
    status_counts: dict[str, int] = Field(default_factory=dict)
    issues: list[OrderIssue] = Field(default_factory=list)
    truncated: bool = False
