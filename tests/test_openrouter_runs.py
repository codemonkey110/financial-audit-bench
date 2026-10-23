"""OpenRouter run robustness: upstream errors, backoff, streaming state, and task image builds.

Provider HTTP is replaced with LiteLLM response objects; Docker is not used.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import litellm
import pytest
from harbor.models.agent.context import AgentContext

from financial_audit_bench import llms
from financial_audit_bench.benchmark import agent
from financial_audit_bench.benchmark.build import pin_apt_snapshot
from financial_audit_bench.llms import LLMResponse

MODEL = "openrouter/google/test-model"


def litellm_response(content: str | None, error: dict | None = None) -> litellm.ModelResponse:
    choice = {"index": 0, "finish_reason": "stop",
              "message": {"role": "assistant", "content": content}}
    if error:
        choice["provider_specific_fields"] = {"error": error, "native_finish_reason": "error"}
    return litellm.ModelResponse(model="google/test-model", choices=[choice],
                                 usage={"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12})


def test_upstream_error_reported_as_empty_choice_is_retried(monkeypatch):
    answers = iter([
        litellm_response(None, {"code": 504, "message": "Upstream idle timeout exceeded"}),
        litellm_response("Done."),
    ])
    calls = []

    async def acompletion(**request):
        calls.append(request)
        return next(answers)

    monkeypatch.setattr(llms, "acompletion", acompletion)
    result = asyncio.run(llms.acomplete(model=MODEL, messages=[{"role": "user", "content": "Hi"}]))
    assert result.content == "Done."
    assert len(calls) == 2


def test_upstream_errors_raise_after_retries(monkeypatch):
    async def acompletion(**request):
        return litellm_response(None, {"code": 504, "message": "Upstream idle timeout exceeded"})

    monkeypatch.setattr(llms, "acompletion", acompletion)
    with pytest.raises(llms.UpstreamProviderError):
        asyncio.run(llms.acomplete(model=MODEL, messages=[{"role": "user", "content": "Hi"}]))


def test_transient_openrouter_errors_back_off_before_retrying(monkeypatch):
    sleeps, attempts = [], iter([True, False])

    async def acompletion(**request):
        if next(attempts):
            raise litellm.RateLimitError("could not verify credits", llm_provider="openrouter", model=MODEL)
        return litellm_response("Done.")

    async def sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr(llms, "acompletion", acompletion)
    monkeypatch.setattr(llms.asyncio, "sleep", sleep)
    result = asyncio.run(llms.acomplete(model=MODEL, messages=[{"role": "user", "content": "Hi"}]))
    assert result.content == "Done."
    assert sleeps == [llms.TRANSIENT_BACKOFF_SECONDS[0]]


def test_streamed_reasoning_text_is_merged_and_signed_blocks_kept():
    details: list[dict] = []
    for item in (
        {"type": "reasoning.text", "index": 0, "text": "Check the "},
        {"type": "reasoning.text", "index": 0, "text": "ledger.", "signature": "sig"},
        {"type": "reasoning.encrypted", "index": 1, "data": "opaque"},
    ):
        llms._merge_reasoning_detail(details, dict(item))
    assert details == [
        {"type": "reasoning.text", "index": 0, "text": "Check the ledger.", "signature": "sig"},
        {"type": "reasoning.encrypted", "index": 1, "data": "opaque"},
    ]


def test_provider_preferences_pin_agent_calls_but_not_the_judge(monkeypatch):
    monkeypatch.setenv("FAB_OPENROUTER_PROVIDER", '{"only": ["google-ai-studio"]}')
    requests = []

    async def acompletion(**request):
        requests.append(request)
        return litellm_response("Done.")

    def completion(**request):
        requests.append(request)
        return litellm_response('{"ok": true}')

    monkeypatch.setattr(llms, "acompletion", acompletion)
    monkeypatch.setattr(llms, "completion", completion)
    asyncio.run(llms.acomplete(model=MODEL, messages=[], reasoning_effort="medium"))
    llms.complete(model="openrouter/openai/judge", messages=[], reasoning_effort="medium")
    assert requests[0]["extra_body"] == {"provider": {"only": ["google-ai-studio"]}}
    assert "reasoning_effort" in requests[0]["allowed_openai_params"]
    assert "extra_body" not in requests[1]


def empty_reply() -> LLMResponse:
    return LLMResponse("", "test-model", {}, 0.0, [], [], {"choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": ""}}]}, 0.1)


def test_consecutive_empty_replies_end_the_trial_as_an_error(tmp_path, monkeypatch):
    calls = []

    async def complete(**kwargs):
        calls.append(kwargs)
        return empty_reply()

    monkeypatch.setattr(agent, "acomplete", complete)
    context = AgentContext()
    runner = agent.AuditAgent(logs_dir=tmp_path, max_model_calls=50)
    with pytest.raises(RuntimeError, match="consecutive empty"):
        asyncio.run(runner.run("Work.", SimpleNamespace(), context))
    assert len(calls) == agent.MAX_EMPTY_RESPONSES
    assert context.metadata["termination_reason"] == "error"


def test_task_images_resolve_apt_from_the_release_snapshot(tmp_path):
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text("FROM python:3.12-slim\nARG LIBREOFFICE_CALC_VERSION=1\nRUN apt-get update\n")
    pin_apt_snapshot(dockerfile)
    lines = dockerfile.read_text().splitlines()
    assert lines[1].startswith("ARG LIBREOFFICE_CALC_VERSION=")
    assert "snapshot.debian.org/archive/debian/" in lines[2]
    assert lines[3] == "RUN apt-get update"


def test_task_images_without_the_dataset_pin_are_left_unchanged(tmp_path):
    dockerfile = tmp_path / "Dockerfile"
    original = "FROM python:3.12-slim\nRUN apt-get update\n"
    dockerfile.write_text(original)
    pin_apt_snapshot(dockerfile)
    assert dockerfile.read_text() == original
