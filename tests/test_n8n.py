import pytest
from pydantic_ai.models.test import TestModel

from core import config
from core.http import ApiError
from n8n import guard, main, tools
from n8n.agent import agent
from n8n.schemas import AgentResult, WorkflowProposal

HTTP = {"type": "n8n-nodes-base.httpRequest", "name": "HTTP", "parameters": {}}
TRIG = {"type": "n8n-nodes-base.scheduleTrigger", "name": "Cron", "parameters": {"a": 1}}
CRED = {**HTTP, "credentials": {"httpBasicAuth": {"id": "1"}}}


@pytest.fixture(autouse=True)
def cfg(monkeypatch):
    monkeypatch.setattr(config, "N8N_URL", "http://n8n.test")
    monkeypatch.setattr(config, "N8N_API_KEY", "k")


def test_agent_is_read_only():
    assert set(agent._function_toolset.tools) == {"list_workflows", "get_workflow", "get_recent_executions"}


def test_guard_safe_change():
    assert guard.check_update([HTTP, TRIG], [{**HTTP, "parameters": {"url": "x"}}, TRIG])[0]


@pytest.mark.parametrize("new", [
    [TRIG],                                                    # hapus node
    [CRED, TRIG],                                              # ubah credential
    [HTTP, {**TRIG, "parameters": {"a": 2}}],                  # ubah trigger
    [HTTP, TRIG, {"type": "n8n-nodes-base.webhook", "name": "W"}],  # tambah trigger
    [{**HTTP, "type": "other"}, TRIG],                         # ubah tipe
])
def test_guard_blocks_risky(new):
    assert not guard.check_update([HTTP, TRIG], new)[0]


def _result(task, proposal):
    return AgentResult(task=task, result="r", proposal=proposal)


def test_fix_safe_is_applied(monkeypatch):
    calls = []
    monkeypatch.setattr(tools, "fetch_workflow", lambda i: {"nodes": [HTTP, TRIG]})
    monkeypatch.setattr(tools, "update_workflow", lambda *a: calls.append(a) or "ok")
    r = main.apply_proposal(_result("fix_workflow", WorkflowProposal(workflow_id="1", nodes=[HTTP, TRIG], connections={})))
    assert r.action_taken == "applied" and len(calls) == 1


def test_fix_risky_is_escalated(monkeypatch):
    calls = []
    monkeypatch.setattr(tools, "fetch_workflow", lambda i: {"nodes": [HTTP, TRIG]})
    monkeypatch.setattr(tools, "update_workflow", lambda *a: calls.append(a))
    r = main.apply_proposal(_result("fix_workflow", WorkflowProposal(workflow_id="1", nodes=[HTTP], connections={})))
    assert r.action_taken == "escalated" and calls == []


def test_api_error_escalates(monkeypatch):
    def boom(i):
        raise ApiError("401")
    monkeypatch.setattr(tools, "fetch_workflow", boom)
    r = main.apply_proposal(_result("fix_workflow", WorkflowProposal(workflow_id="1", nodes=[HTTP], connections={})))
    assert r.action_taken == "escalated"


def test_fetch_workflows_paginates_and_errors(monkeypatch):
    pages = iter([
        {"data": [{"id": "1", "name": "a", "active": True}], "nextCursor": "c"},
        {"data": [{"id": "2", "name": "b", "active": False}], "nextCursor": None},
    ])

    class R:
        status_code = 200
        text = ""
        def json(self): return next(pages)

    monkeypatch.setattr("requests.request", lambda *a, **k: R())
    assert [w["id"] for w in tools.fetch_workflows()] == ["1", "2"]

    class Bad(R):
        status_code = 401
    monkeypatch.setattr("requests.request", lambda *a, **k: Bad())
    with pytest.raises(ApiError):
        tools.fetch_workflows()


def test_health_check_end_to_end_with_test_model(monkeypatch):
    out = AgentResult(task="health_check", result="ok").model_dump()
    monkeypatch.setattr(main, "get_ollama_model", lambda: TestModel(custom_output_args=out, call_tools=[]))
    assert main.run_health_check().task == "health_check"
