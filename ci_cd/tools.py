"""Tool GitLab -- fungsi biasa, bisa di-unit-test tanpa memanggil LLM sama sekali."""

import re

from core import config
from core.http import request

_SECRET_PATTERNS = [
    re.compile(r"(?i)((?:token|password|passwd|secret|api[_-]?key|authorization)\S{0,20}?[=:]\s*)\S+"),
    re.compile(r"glpat-[A-Za-z0-9_\-]{10,}"),
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-]{10,}"),
]


def _headers() -> dict:
    return {"PRIVATE-TOKEN": config.GITLAB_TOKEN}


def _get(path: str, **kwargs):
    return request("GET", f"{config.GITLAB_URL}/api/v4{path}", require_base=config.GITLAB_URL,
                   headers=_headers(), **kwargs)


def redact_secrets(text: str) -> str:
    text = _SECRET_PATTERNS[0].sub(r"\1[REDACTED]", text)
    text = _SECRET_PATTERNS[1].sub("[REDACTED]", text)
    return _SECRET_PATTERNS[2].sub(r"\1[REDACTED]", text)


def fetch_failed_job_log(project_id: int, pipeline_id: int) -> str:
    jobs = _get(f"/projects/{project_id}/pipelines/{pipeline_id}/jobs",
                params={"per_page": 100, "scope[]": "failed"}).json()

    failed = next((j for j in jobs if j.get("status") == "failed" and not j.get("allow_failure")), None)
    if not failed:
        return "No failed job found in this pipeline."

    log = _get(f"/projects/{project_id}/jobs/{failed['id']}/trace").text
    return redact_secrets(log[-4000:])


def post_mr_comment(project_id: int, mr_iid: int | None, body: str) -> str:
    if not mr_iid:
        return "No MR associated with this pipeline; comment skipped."
    resp = request("POST", f"{config.GITLAB_URL}/api/v4/projects/{project_id}/merge_requests/{mr_iid}/notes",
                   require_base=config.GITLAB_URL, headers=_headers(), json={"body": body})
    return f"Comment posted (status {resp.status_code})."


def retry_job(project_id: int, job_id: int) -> str:
    """Tidak didaftarkan sebagai tool agent -- hanya dipanggil manusia/kode setelah approval."""
    resp = request("POST", f"{config.GITLAB_URL}/api/v4/projects/{project_id}/jobs/{job_id}/retry",
                   require_base=config.GITLAB_URL, headers=_headers())
    return f"Retry triggered (status {resp.status_code})."
