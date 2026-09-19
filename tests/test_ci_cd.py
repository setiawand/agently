import pytest
from pydantic_ai.models.test import TestModel

from ci_cd import tools, main
from ci_cd.agent import agent
from ci_cd.schemas import Deps, Diagnosis
from core import config
from core.http import ApiError


class FakeResp:
    def __init__(self, status=200, json_data=None, text=""):
        self.status_code, self._json, self.text = status, json_data, text

    def json(self):
        return self._json


@pytest.fixture(autouse=True)
def cfg(monkeypatch):
    monkeypatch.setattr(config, "GITLAB_URL", "https://gl.test")
    monkeypatch.setattr(config, "GITLAB_TOKEN", "t")


def test_agent_has_no_write_tools():
    names = set(agent._function_toolset.tools)
    assert names == {"get_failed_job_log"}


def test_http_error_raises(monkeypatch):
    monkeypatch.setattr("requests.request", lambda *a, **k: FakeResp(401, text="unauthorized"))
    with pytest.raises(ApiError):
        tools.fetch_failed_job_log(1, 2)


def test_missing_base_url(monkeypatch):
    monkeypatch.setattr(config, "GITLAB_URL", "")
    with pytest.raises(ApiError):
        tools.fetch_failed_job_log(1, 2)


def test_skips_allow_failure_and_redacts(monkeypatch):
    def fake(method, url, **kw):
        if url.endswith("/jobs"):
            return FakeResp(json_data=[
                {"id": 1, "status": "failed", "allow_failure": True},
                {"id": 2, "status": "failed", "allow_failure": False},
            ])
        assert "/jobs/2/trace" in url
        return FakeResp(text="boom\nGITLAB_TOKEN=abc123 glpat-abcdefghijklmnop")

    monkeypatch.setattr("requests.request", fake)
    log = tools.fetch_failed_job_log(1, 2)
    assert "abc123" not in log and "glpat-abc" not in log and "boom" in log


def _run_with(monkeypatch, action, confidence, mr_iid=7):
    posted = []
    monkeypatch.setattr(tools, "post_mr_comment", lambda *a: posted.append(a))
    monkeypatch.setattr(tools, "fetch_failed_job_log", lambda *a: "log")
    out = Diagnosis(root_cause="x", confidence=confidence, suggested_action=action, comment_text="c")
    with agent.override(model=TestModel(custom_output_args=out.model_dump())):
        monkeypatch.setattr(main, "get_model", lambda: TestModel(custom_output_args=out.model_dump()))
        main.diagnose_pipeline(1, 2, mr_iid)
    return posted


def test_gate_comments_only_when_confident(monkeypatch):
    assert len(_run_with(monkeypatch, "comment", 0.9)) == 1
    assert _run_with(monkeypatch, "comment", 0.3) == []
    assert _run_with(monkeypatch, "comment", 0.9, mr_iid=None) == []


@pytest.mark.parametrize("action", ["rerun", "escalate"])
def test_gate_never_auto_acts_on_risky(monkeypatch, action):
    retried = []
    monkeypatch.setattr(tools, "retry_job", lambda *a: retried.append(a))
    assert _run_with(monkeypatch, action, 1.0) == []
    assert retried == []
