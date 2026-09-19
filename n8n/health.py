"""Klasifikasi health check secara deterministik -- tanpa LLM."""

from n8n.schemas import HealthReport, WorkflowIssue

_FAILED = {"error", "crashed", "failed"}


def build_report(data: list[dict]) -> HealthReport:
    issues: list[WorkflowIssue] = []
    healthy = 0
    for w in data:
        base = {"workflow_id": w["id"], "workflow_name": w["name"]}
        if not w["active"]:
            issues.append(WorkflowIssue(**base, status="inactive", detail="Workflow tidak aktif."))
        elif w.get("error"):
            issues.append(WorkflowIssue(**base, status="error", detail=f"Gagal membaca eksekusi: {w['error']}"))
        elif w["executions"] and w["executions"][0].get("status") in _FAILED:
            last = w["executions"][0]
            statuses = ", ".join(str(e.get("status")) for e in w["executions"])
            issues.append(WorkflowIssue(
                **base, status="failing",
                detail=f"Eksekusi terakhir {last.get('status')} (id {last['id']}, {last.get('startedAt')}). "
                       f"Riwayat terbaru: {statuses}.",
            ))
        else:
            healthy += 1

    counts = {s: sum(1 for i in issues if i.status == s) for s in ("failing", "error", "inactive")}
    summary = (
        f"{len(data)} workflow: {healthy} sehat, {counts['failing']} gagal, "
        f"{counts['error']} tidak bisa dicek, {counts['inactive']} inactive."
    )
    issues.sort(key=lambda i: ("failing", "error", "inactive").index(i.status))
    return HealthReport(summary=summary, issues=issues)
