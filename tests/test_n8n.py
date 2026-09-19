import pytest
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


def test_health_report_classification():
    from n8n import health
    data = [
        {"id": "1", "name": "ok", "active": True, "executions": [{"id": "9", "status": "success"}]},
        {"id": "2", "name": "bad", "active": True, "executions": [{"id": "8", "status": "error", "startedAt": "t"}]},
        {"id": "3", "name": "off", "active": False, "executions": []},
        {"id": "4", "name": "noexec", "active": True, "executions": [], "error": "HTTP 500"},
    ]
    r = health.build_report(data)
    assert [i.status for i in r.issues] == ["failing", "error", "inactive"]
    assert "1 sehat" in r.summary and "4 workflow" in r.summary


def test_run_health_check_does_not_call_llm(monkeypatch):
    monkeypatch.setattr(tools, "fetch_health_data", lambda progress=None: [{"id": "1", "name": "a", "active": False, "executions": []}])
    monkeypatch.setattr(main, "get_ollama_model", lambda: (_ for _ in ()).throw(AssertionError("LLM dipanggil")))
    r = main.run_health_check()
    assert r.task == "health_check" and r.report.issues[0].status == "inactive"


def test_fetch_health_data_isolates_errors(monkeypatch):
    monkeypatch.setattr(tools, "fetch_workflows", lambda: [
        {"id": "1", "name": "a", "active": True}, {"id": "2", "name": "b", "active": False}])
    def execs(i, n):
        raise ApiError("boom")
    monkeypatch.setattr(tools, "fetch_recent_executions", execs)
    d = tools.fetch_health_data()
    assert "error" in d[0] and d[1]["executions"] == []


def test_fetch_health_data_reports_progress(monkeypatch):
    monkeypatch.setattr(tools, "fetch_workflows", lambda: [
        {"id": str(i), "name": f"w{i}", "active": False} for i in range(3)])
    seen = []
    d = tools.fetch_health_data(progress=lambda done, total, name: seen.append((done, total)))
    assert [w["id"] for w in d] == ["0", "1", "2"]
    assert seen == [(0, 3), (1, 3), (2, 3), (3, 3)]


def test_explain_failures(monkeypatch):
    from pydantic_ai.models.test import TestModel
    from n8n import explain

    monkeypatch.setattr(tools, "fetch_health_data", lambda progress=None: [
        {"id": "1", "name": "bad", "active": True, "executions": [{"id": "8", "status": "error"}]},
        {"id": "2", "name": "ok", "active": True, "executions": [{"id": "9", "status": "success"}]},
    ])
    monkeypatch.setattr(tools, "fetch_recent_executions", lambda i, n: [{"id": "8"}])
    monkeypatch.setattr(tools, "fetch_execution_error", lambda i: {"node": "HTTP", "message": "401"})
    monkeypatch.setattr(explain, "get_ollama_model", lambda name=None: TestModel(custom_output_text="Token kedaluwarsa."))
    r = explain.explain_failures()
    assert len(r) == 1 and r[0].error_node == "HTTP" and r[0].explanation == "Token kedaluwarsa."


def test_explain_failures_survives_llm_error(monkeypatch):
    from n8n import explain

    monkeypatch.setattr(tools, "fetch_health_data", lambda progress=None: [
        {"id": "1", "name": "bad", "active": True, "executions": [{"id": "8", "status": "error"}]}])
    monkeypatch.setattr(tools, "fetch_recent_executions", lambda i, n: [{"id": "8"}])
    monkeypatch.setattr(tools, "fetch_execution_error", lambda i: {"node": "HTTP", "message": "401"})

    class Boom:
        def __getattr__(self, n): raise RuntimeError("down")
    monkeypatch.setattr(explain, "get_ollama_model", lambda name=None: Boom())
    r = explain.explain_failures()
    assert r[0].error_message == "401" and r[0].explanation.startswith("(LLM gagal")


_DATA = [
    {"id": "1", "name": "bad", "active": True, "executions": [{"id": "8", "status": "error", "startedAt": "t"}]},
    {"id": "2", "name": "off", "active": False, "executions": []},
]


def test_summarize_health_uses_llm_and_falls_back(monkeypatch):
    from pydantic_ai.models.test import TestModel
    from n8n import explain

    monkeypatch.setattr(tools, "fetch_health_data", lambda progress=None: _DATA)
    monkeypatch.setattr(explain, "get_ollama_model", lambda name=None: TestModel(custom_output_text="Ada 1 workflow gagal."))
    assert explain.summarize_health() == "Ada 1 workflow gagal."

    class Boom:
        def __getattr__(self, n): raise RuntimeError("down")
    monkeypatch.setattr(explain, "get_ollama_model", lambda name=None: Boom())
    out = explain.summarize_health()
    assert "2 workflow" in out and "gagal" in out
