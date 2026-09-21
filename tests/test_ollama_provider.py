import json

import httpx
import pytest

from browser_agent.config import Settings
from browser_agent.llm import InvalidDecision, ProviderError
from browser_agent.ollama_provider import OllamaProvider


def provider(handler):
    return OllamaProvider(
        Settings(),
        httpx.AsyncClient(
            base_url="http://127.0.0.1:11434", transport=httpx.MockTransport(handler)
        ),
    )


def response(calls):
    return {"done": True, "done_reason": "stop", "message": {"tool_calls": calls}}


async def test_local_model_uses_native_tools_without_credentials():
    def handler(request):
        assert "authorization" not in request.headers
        body = json.loads(request.content)
        assert body["think"] is False
        assert body["tools"][0]["function"]["name"] == "navigate"
        return httpx.Response(
            200, json=response([{"function": {"name": "wait", "arguments": {"milliseconds": 100}}}])
        )

    instance = provider(handler)
    try:
        assert (await instance.decide("page")).name == "wait"
    finally:
        await instance.close()


@pytest.mark.parametrize(
    "calls",
    [
        [],
        [{"function": {"name": "shell", "arguments": {}}}],
        [{"function": {"name": "wait", "arguments": {"milliseconds": 100}}}] * 2,
        [{"function": {"name": "wait", "arguments": {"milliseconds": "100"}}}],
    ],
)
async def test_local_model_invalid_actions_never_reach_browser(calls):
    instance = provider(lambda _: httpx.Response(200, json=response(calls)))
    try:
        with pytest.raises(InvalidDecision):
            await instance.decide("page")
    finally:
        await instance.close()


async def test_local_verifier_uses_constrained_json():
    def handler(request):
        body = json.loads(request.content)
        assert body["format"]["additionalProperties"] is False
        assert "tools" not in body
        return httpx.Response(
            200,
            json={
                "done": True,
                "message": {
                    "content": json.dumps(
                        {"complete": False, "evidence": "Empty", "feedback": "Continue"}
                    )
                },
            },
        )

    instance = provider(handler)
    try:
        assert not (await instance.verify("page", "Done")).complete
    finally:
        await instance.close()


async def test_missing_local_model_has_actionable_error():
    instance = provider(lambda _: httpx.Response(404))
    try:
        with pytest.raises(ProviderError, match="ollama pull"):
            await instance.decide("page")
    finally:
        await instance.close()


def test_local_provider_cannot_send_page_to_remote_endpoint():
    with pytest.raises(ValueError, match="local"):
        OllamaProvider(Settings(ollama_url="https://example.org"))


async def test_local_tool_history_is_bounded_and_receives_fresh_state():
    bodies = []

    def handler(request):
        bodies.append(json.loads(request.content))
        return httpx.Response(
            200, json=response([{"function": {"name": "wait", "arguments": {"milliseconds": 100}}}])
        )

    instance = provider(handler)
    try:
        for step in range(8):
            await instance.decide(
                json.dumps({"user_goal": "Read the page", "user_answers": [], "step": step})
            )
        messages = bodies[-1]["messages"]
        assert len(messages) == 4
        assert "Read the page" in messages[1]["content"]
        assert messages[2]["tool_calls"][0]["function"]["name"] == "wait"
        assert messages[3]["role"] == "tool"
        assert '"step": 7' in messages[3]["content"]
    finally:
        await instance.close()


async def test_invalid_argument_feedback_names_field_without_echoing_input():
    instance = provider(
        lambda _: httpx.Response(
            200,
            json=response(
                [{"function": {"name": "click", "arguments": {"element_id": "private-value"}}}]
            ),
        )
    )
    try:
        with pytest.raises(InvalidDecision) as failure:
            await instance.decide("page")
        assert "risk: missing" in str(failure.value)
        assert "private-value" not in str(failure.value)
    finally:
        await instance.close()
