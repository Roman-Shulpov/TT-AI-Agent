"""Real local inference via Ollama's native tool-calling API; no scripted decisions."""

import asyncio
import json
import logging
import time
from urllib.parse import urlsplit

import httpx
from pydantic import ValidationError

from .config import Settings
from .llm import DESCRIPTIONS, InvalidDecision, ProviderError
from .models import TOOL_MODELS, Action, Verification
from .prompts import SYSTEM_PROMPT, VERIFIER_PROMPT

logger = logging.getLogger(__name__)


class OllamaProvider:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None):
        url = urlsplit(settings.ollama_url)
        if url.scheme != "http" or url.hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("Ollama must use a local HTTP endpoint")
        self.model = settings.llm_model
        self.context_tokens = settings.ollama_context_tokens
        self.previous_call: dict | None = None
        self.client = client or httpx.AsyncClient(
            base_url=settings.ollama_url, timeout=settings.llm_timeout_seconds, trust_env=False
        )
        self.tools = [
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": DESCRIPTIONS[name],
                    "parameters": model.model_json_schema(),
                },
            }
            for name, model in TOOL_MODELS.items()
        ]

    async def close(self) -> None:
        await self.client.aclose()

    async def _request(self, body: dict) -> dict:
        for attempt in range(3):
            started = time.monotonic()
            try:
                response = await self.client.post(
                    "/api/chat",
                    json={
                        "model": self.model,
                        "stream": False,
                        "think": False,
                        "keep_alive": "15m",
                        "options": {
                            "temperature": 0,
                            "num_ctx": self.context_tokens,
                            "num_predict": 1200,
                        },
                        **body,
                    },
                )
                if response.status_code == 404:
                    raise ProviderError(f"Local model missing. Run: ollama pull {self.model}")
                if response.status_code >= 500 or response.status_code == 429:
                    raise httpx.RequestError("Local inference temporarily unavailable")
                if response.is_error:
                    raise ProviderError(f"Local model HTTP {response.status_code}")
                data = response.json()
                if not isinstance(data, dict) or data.get("done") is not True:
                    raise InvalidDecision("Incomplete local model response")
                if data.get("done_reason") == "length":
                    raise InvalidDecision("Local model output hit token limit")
                logger.info(
                    "LLM local latency=%.2fs input_tokens=%s output_tokens=%s",
                    time.monotonic() - started,
                    data.get("prompt_eval_count"),
                    data.get("eval_count"),
                )
                return data
            except (httpx.RequestError, httpx.TimeoutException):
                if attempt == 2:
                    raise ProviderError(
                        "Local model unavailable. Start Ollama and retry."
                    ) from None
                logger.warning("Local inference retry=%s", attempt + 1)
                await asyncio.sleep(0.5 * 2**attempt)
            except (ValueError, TypeError):
                raise InvalidDecision("Local model returned malformed JSON") from None
        raise ProviderError("Local model retry budget exhausted")

    async def decide(self, context: str) -> Action:
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        if self.previous_call is not None:
            state = json.loads(context)
            messages.extend(
                [
                    {
                        "role": "user",
                        "content": "Continue this task from the updated browser state.\n"
                        + json.dumps(
                            {
                                "user_goal": state["user_goal"],
                                "user_answers": state["user_answers"],
                            },
                            ensure_ascii=False,
                        ),
                    },
                    {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [{"function": self.previous_call}],
                    },
                    {
                        "role": "tool",
                        "tool_name": self.previous_call["name"],
                        "content": "State after the proposed action. "
                        "Receipts/feedback describe whether it executed:\n" + context,
                    },
                ]
            )
        else:
            messages.append({"role": "user", "content": context})
        data = await self._request(
            {
                "messages": messages,
                "tools": self.tools,
            }
        )
        try:
            calls = data["message"].get("tool_calls", [])
            if len(calls) != 1:
                raise InvalidDecision("Call exactly one tool. Do not answer with plain text.")
            call = calls[0]["function"]
            action = Action.parse(call["name"], json.dumps(call["arguments"], ensure_ascii=False))
            self.previous_call = {"name": action.name, "arguments": action.arguments.model_dump()}
            return action
        except ValidationError as exc:
            fields = ", ".join(
                f"{'.'.join(map(str, item['loc']))}: {item['type']}"
                for item in exc.errors(include_input=False, include_url=False)
            )
            raise InvalidDecision(
                "Invalid tool arguments; correct these fields: " + fields
            ) from None
        except (KeyError, AttributeError, TypeError, ValueError):
            raise InvalidDecision(
                "Invalid local tool name/arguments; follow the tool schema"
            ) from None

    async def verify(self, context: str, proposal: str) -> Verification:
        # Constrained structured output is suitable for the verifier's single fixed schema.
        data = await self._request(
            {
                "messages": [
                    {
                        "role": "system",
                        "content": VERIFIER_PROMPT.replace(
                            "Use only the verification function.",
                            "Return only the requested JSON object.",
                        ),
                    },
                    {"role": "user", "content": context + "\nUNPROVEN PROPOSAL:\n" + proposal},
                ],
                "format": Verification.model_json_schema(),
            }
        )
        try:
            return Verification.model_validate_json(data["message"]["content"])
        except (KeyError, TypeError, ValueError, ValidationError):
            raise InvalidDecision("Invalid local verification response") from None
