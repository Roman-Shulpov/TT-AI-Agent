"""Official OpenAI SDK / Responses native tools and shared provider interface."""

import asyncio
import logging
import time
from typing import Protocol

from openai import APIConnectionError, APIStatusError, AsyncOpenAI, RateLimitError
from pydantic import ValidationError

from .config import Settings
from .models import TOOL_MODELS, Action, StrictModel, Verification
from .prompts import SYSTEM_PROMPT, VERIFIER_PROMPT

logger = logging.getLogger(__name__)

DESCRIPTIONS = {
    "navigate": "Open an absolute HTTP(S) URL supplied by the user or grounded in the page.",
    "click": "Click a current element ID. Classify risk; runtime enforces confirmation.",
    "type_text": "Replace text in an editable element. Do not enter passwords or API keys.",
    "select_option": "Choose a native select option by its observed value.",
    "scroll": "Scroll main document to discover more visible content.",
    "go_back": "Navigate back in current tab history.",
    "wait": "Wait 100–2000 ms only if a dynamic update is pending.",
    "press_key": "Press one allowed key on an element. Enter/Space may submit; classify risk.",
    "switch_tab": "Switch to a tab ID from the current observation.",
    "ask_user": "Ask for missing information or manual login/CAPTCHA assistance.",
    "record_fact": "Save a verbatim visible quote with source URL in bounded memory.",
    "finish": "Propose completion with summary and observed evidence for independent verification.",
}


class ProviderError(Exception):
    """Sanitized provider failure safe to show without leaking payloads or credentials."""


class InvalidDecision(ProviderError):
    pass


class DecisionProvider(Protocol):
    async def decide(self, context: str) -> Action: ...

    async def verify(self, context: str, proposal: str) -> Verification: ...

    async def close(self) -> None: ...


def function_schema(name: str, model: type[StrictModel], description: str) -> dict:
    return {
        "type": "function",
        "name": name,
        "description": description,
        "parameters": model.model_json_schema(),
        "strict": True,
    }


class OpenAIProvider:
    def __init__(self, settings: Settings, client: AsyncOpenAI | None = None):
        self.model = settings.llm_model
        self.key = settings.llm_api_key.get_secret_value()
        self.client = client or AsyncOpenAI(
            api_key=self.key,
            base_url=settings.llm_base_url,
            timeout=settings.llm_timeout_seconds,
            max_retries=0,
        )
        self.tools = [
            function_schema(name, model, DESCRIPTIONS[name]) for name, model in TOOL_MODELS.items()
        ]

    async def close(self) -> None:
        await self.client.close()

    async def _call(self, instructions: str, content: str, schemas: list[dict]) -> tuple[str, str]:
        started = time.monotonic()
        # The provider key itself must never occur in model input, even if pasted into a goal.
        if self.key:
            content = content.replace(self.key, "[redacted]")
        for attempt in range(3):
            try:
                response = await self.client.responses.create(
                    model=self.model,
                    instructions=instructions,
                    input=[{"role": "user", "content": content}],
                    tools=schemas,
                    tool_choice="required",
                    parallel_tool_calls=False,
                    store=False,
                    max_output_tokens=1800,
                )
                calls = [item for item in response.output if item.type == "function_call"]
                if response.status != "completed" or len(calls) != 1:
                    raise InvalidDecision("Expected one completed function call; replan")
                if self.key and self.key in calls[0].arguments:
                    raise InvalidDecision("Output contained a protected credential")
                tokens = response.usage.total_tokens if response.usage else None
                logger.info("LLM latency=%.2fs tokens=%s", time.monotonic() - started, tokens)
                return calls[0].name, calls[0].arguments
            except (APIConnectionError, RateLimitError) as exc:
                retryable = exc
            except APIStatusError as exc:
                if exc.status_code < 500:
                    raise ProviderError(
                        f"LLM HTTP {exc.status_code}; check configuration/access"
                    ) from None
                retryable = exc
            if attempt == 2:
                raise ProviderError(
                    f"LLM unavailable after 3 attempts: {type(retryable).__name__}"
                ) from None
            logger.warning("LLM transient error=%s retry=%s", type(retryable).__name__, attempt + 1)
            await asyncio.sleep(0.5 * 2**attempt)
        raise ProviderError("Retry budget exhausted")

    async def decide(self, context: str) -> Action:
        name, arguments = await self._call(SYSTEM_PROMPT, context, self.tools)
        try:
            return Action.parse(name, arguments)
        except (ValueError, ValidationError):
            raise InvalidDecision(
                "Invalid tool name/arguments; use current IDs and exact schema"
            ) from None

    async def verify(self, context: str, proposal: str) -> Verification:
        name, arguments = await self._call(
            VERIFIER_PROMPT,
            context + "\nUNPROVEN COMPLETION PROPOSAL:\n" + proposal,
            [
                function_schema(
                    "verification",
                    Verification,
                    "Assess whether observed evidence proves completion",
                )
            ],
        )
        if name != "verification":
            raise InvalidDecision("Verifier returned wrong tool")
        try:
            return Verification.model_validate_json(arguments)
        except ValidationError:
            raise InvalidDecision("Verifier returned invalid structured result") from None
