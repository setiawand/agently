"""Trace lokal aktivitas agent (tanpa layanan luar): AGENTLY_TRACE=1 -> tiap langkah model tampil di stderr."""

import asyncio
import sys
import time

from pydantic_ai import Agent
from pydantic_ai.messages import (
    RetryPromptPart, TextPart, ThinkingPart, ToolCallPart, ToolReturnPart, UserPromptPart,
)

from core import config

_MAX = 400


def _clip(x) -> str:
    s = str(x).replace("\n", " ⏎ ")
    return s if len(s) <= _MAX else s[:_MAX] + f"... (+{len(s) - _MAX} char)"


def _log(t0: float, msg: str) -> None:
    print(f"[trace +{time.monotonic() - t0:6.1f}s] {msg}", file=sys.stderr, flush=True)


def _show(node, t0: float) -> None:
    if Agent.is_model_request_node(node):
        for p in node.request.parts:
            if isinstance(p, UserPromptPart):
                _log(t0, f"PROMPT   -> model: {_clip(p.content)}")
            elif isinstance(p, ToolReturnPart):
                _log(t0, f"TOOL OUT -> model: {p.tool_name}: {_clip(p.content)}")
            elif isinstance(p, RetryPromptPart):
                _log(t0, f"RETRY    -> model: {_clip(p.content)}")
        _log(t0, "menunggu model...")
    elif Agent.is_call_tools_node(node):
        for p in node.model_response.parts:
            if isinstance(p, ThinkingPart):
                _log(t0, f"THINKING: {_clip(p.content)}")
            elif isinstance(p, ToolCallPart):
                _log(t0, f"TOOL CALL: {p.tool_name}({_clip(p.args)})")
            elif isinstance(p, TextPart):
                _log(t0, f"MODEL    : {_clip(p.content)}")
        u = node.model_response.usage
        _log(t0, f"usage: in={u.input_tokens} out={u.output_tokens}")


def run_agent(agent: Agent, prompt: str, *, model, deps=None):
    """agent.run_sync, plus trace langkah demi langkah bila AGENTLY_TRACE aktif."""
    if not config.TRACE:
        return agent.run_sync(prompt, deps=deps, model=model)

    async def go():
        t0 = time.monotonic()
        async with agent.iter(prompt, deps=deps, model=model) as run:
            async for node in run:
                _show(node, t0)
            _log(t0, f"selesai. total usage: {run.usage}")
            return run.result

    return asyncio.run(go())
