import json

import httpx
import pytest
from openai import AsyncOpenAI
from pydantic import SecretStr

from browser_agent.config import Settings
from browser_agent.llm import InvalidDecision, OpenAIProvider, ProviderError


def response_body(name="wait", arguments='{"milliseconds":100}', count=1):
    return {
        "id": "resp_test",
        "object": "response",
        "created_at": 1,
        "status": "completed",
        "model": "test-model",
        "output": [
            {
                "type": "function_call",
                "id": f"fc_{i}",
                "call_id": f"call_{i}",
                "name": name,
                "arguments": arguments,
                "status": "completed",
            }
            for i in range(count)
        ],
        "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
    }


def provider(handler):
    client = AsyncOpenAI(
        api_key="test-protected-key",
        base_url="https://provider.invalid/v1",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        max_retries=0,
    )
    return OpenAIProvider(Settings(llm_api_key=SecretStr("test-protected-key")), client)


async def test_official_sdk_serializes_native_strict_function_call():
    requests = []

    def handler(request):
        requests.append(json.loads(request.content))
        assert request.url.path == "/v1/responses"
        return httpx.Response(200, json=response_body())

    instance = provider(handler)
    try:
        decision = await instance.decide("Test observation test-protected-key")
    finally:
        await instance.close()
    assert decision.name == "wait"
    body = requests[0]
    assert body["parallel_tool_calls"] is False
    assert body["store"] is False
    assert body["tool_choice"] == "required"
    assert all(t["strict"] for t in body["tools"])
    assert "test-protected-key" not in json.dumps(body)


@pytest.mark.parametrize(
    "payload",
    [
        response_body(count=0),
        response_body(count=2),
        response_body(arguments='{"milliseconds":99999}'),
        response_body(name="shell"),
    ],
)
async def test_invalid_provider_decisions_rejected(payload):
    instance = provider(lambda _: httpx.Response(200, json=payload))
    try:
        with pytest.raises(InvalidDecision):
            await instance.decide("observation")
    finally:
        await instance.close()


async def test_rate_limit_then_recovery():
    attempts = 0

    def handler(_):
        nonlocal attempts
        attempts += 1
        return (
            httpx.Response(429, json={"error": {"message": "rate limit"}})
            if attempts < 3
            else (httpx.Response(200, json=response_body()))
        )

    instance = provider(handler)
    try:
        assert (await instance.decide("observation")).name == "wait"
    finally:
        await instance.close()
    assert attempts == 3


async def test_auth_failure_is_not_retried_or_leaked():
    attempts = 0

    def handler(_):
        nonlocal attempts
        attempts += 1
        return httpx.Response(401, json={"error": {"message": "sensitive payload"}})

    instance = provider(handler)
    try:
        with pytest.raises(ProviderError, match="HTTP 401") as caught:
            await instance.decide("observation")
    finally:
        await instance.close()
    assert attempts == 1
    assert "sensitive payload" not in str(caught.value)


async def test_verifier_uses_its_own_strict_schema():
    def handler(request):
        body = json.loads(request.content)
        assert [t["name"] for t in body["tools"]] == ["verification"]
        return httpx.Response(
            200,
            json=response_body(
                "verification",
                json.dumps(
                    {"complete": False, "evidence": "Empty cart", "feedback": "Add an item"}
                ),
            ),
        )

    instance = provider(handler)
    try:
        assert not (await instance.verify("observation", "Done")).complete
    finally:
        await instance.close()
