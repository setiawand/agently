"""Tool n8n REST API -- fungsi biasa, bisa di-unit-test tanpa LLM.

Catatan: auth n8n pakai header X-N8N-API-KEY, bukan Bearer token.
Fungsi tulis (create/update/set_active) TIDAK didaftarkan sebagai tool agent;
dipanggil dari n8n/main.py setelah melewati n8n/guard.py.
"""

from typing import Any

from core import config
from core.http import request

_MAX_PAGES = 20


def _headers() -> dict:
    return {"X-N8N-API-KEY": config.N8N_API_KEY, "Content-Type": "application/json"}


def _call(method: str, path: str, **kwargs):
    return request(method, f"{config.N8N_URL}/api/v1{path}", require_base=config.N8N_URL,
                   headers=_headers(), **kwargs)


def fetch_workflows() -> list[dict]:
    items: list[dict] = []
    cursor = None
    for _ in range(_MAX_PAGES):
        params: dict[str, Any] = {"limit": 100}
        if cursor:
            params["cursor"] = cursor
        body = _call("GET", "/workflows", params=params).json()
        items += body.get("data", [])
        cursor = body.get("nextCursor")
        if not cursor:
            break
    return [{"id": w["id"], "name": w["name"], "active": w["active"]} for w in items]


def fetch_workflow(workflow_id: str) -> dict:
    """Detail workflow tanpa pinData/staticData (boros token, bisa berisi data sensitif)."""
    wf = _call("GET", f"/workflows/{workflow_id}").json()
    wf.pop("pinData", None)
    wf.pop("staticData", None)
    return wf


def fetch_recent_executions(workflow_id: str, limit: int = 5) -> list[dict]:
    limit = max(1, min(limit, 20))
    data = _call("GET", "/executions", params={"workflowId": workflow_id, "limit": limit}).json().get("data", [])
    return [{"id": e["id"], "status": e.get("status"), "startedAt": e.get("startedAt")} for e in data]


def create_workflow(name: str, nodes: list[dict], connections: dict[str, Any]) -> str:
    """Workflow baru dibuat inactive (default n8n); aktivasi tetap manual."""
    payload = {"name": name, "nodes": nodes, "connections": connections, "settings": {}}
    resp = _call("POST", "/workflows", json=payload)
    return f"Workflow '{name}' berhasil dibuat (inactive) dengan id {resp.json().get('id')}."


def update_workflow(workflow_id: str, nodes: list[dict], connections: dict[str, Any]) -> str:
    """n8n v1 memakai PUT dengan objek lengkap (name, nodes, connections, settings)."""
    current = _call("GET", f"/workflows/{workflow_id}").json()
    payload = {
        "name": current["name"],
        "nodes": nodes,
        "connections": connections,
        "settings": current.get("settings", {}),
    }
    _call("PUT", f"/workflows/{workflow_id}", json=payload)
    return "Workflow berhasil diupdate."


def set_workflow_active(workflow_id: str, active: bool) -> str:
    action = "activate" if active else "deactivate"
    resp = _call("POST", f"/workflows/{workflow_id}/{action}")
    return f"Workflow {'diaktifkan' if active else 'dinonaktifkan'} (status {resp.status_code})."


def fetch_health_data(max_workers: int = 8) -> list[dict]:
    """Semua workflow + status eksekusi terakhir (paralel). Workflow inactive tidak perlu dicek eksekusinya."""
    from concurrent.futures import ThreadPoolExecutor

    from core.http import ApiError

    def one(w: dict) -> dict:
        if not w["active"]:
            return {**w, "executions": []}
        try:
            return {**w, "executions": fetch_recent_executions(w["id"], 3)}
        except ApiError as e:
            return {**w, "executions": [], "error": str(e)}

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        return list(pool.map(one, fetch_workflows()))
