"""Use the official authenticated Codex CLI for schema-constrained decisions.

Credentials remain managed by the CLI. The subprocess gets the prompt on stdin,
an empty temporary working directory, read-only sandbox and disabled integrations.
Only the validated response is executed by our browser runtime.
"""

import asyncio
import json
import logging
import shutil
import tempfile
import time
from pathlib import Path

from pydantic import ValidationError

from .config import Settings
from .llm import DESCRIPTIONS, InvalidDecision, ProviderError
from .models import TOOL_MODELS, Action, Verification
from .prompts import SYSTEM_PROMPT, VERIFIER_PROMPT

logger = logging.getLogger(__name__)


def cli_command() -> list[str]:
    executable = shutil.which("codex")
    if not executable:
        raise ProviderError("Install Codex CLI and run codex login, or select another provider.")
    path = Path(executable)
    if path.suffix.lower() in {".cmd", ".bat", ".ps1"}:
        # Find npm's native binary; avoid both shell interpolation and a wrapper child process.
        package = path.parent / "node_modules/@openai/codex"
        for pattern in (
            "node_modules/@openai/codex-*/vendor/*/bin/codex.exe",
            "node_modules/@openai/codex-*/vendor/*/codex/codex.exe",
            "vendor/*/codex/codex.exe",
        ):
            candidates = list(package.glob(pattern))
            if len(candidates) == 1:
                return [str(candidates[0])]
        raise ProviderError("Cannot locate the native Codex npm binary. Reinstall Codex CLI.")
    return [executable]


def action_schema() -> dict:
    variants = [
        {
            "type": "object",
            "properties": {
                "name": {"type": "string", "enum": [name]},
                "arguments": model.model_json_schema(),
            },
            "required": ["name", "arguments"],
            "additionalProperties": False,
        }
        for name, model in TOOL_MODELS.items()
    ]
    return {
        "type": "object",
        "properties": {"action": {"anyOf": variants}},
        "required": ["action"],
        "additionalProperties": False,
    }


class CodexProvider:
    def __init__(self, settings: Settings):
        self.command = cli_command()
        self.model = settings.llm_model
        self.timeout = settings.llm_timeout_seconds

    async def close(self) -> None:
        pass

    async def _request(self, prompt: str, schema: dict) -> dict:
        started = time.monotonic()
        with tempfile.TemporaryDirectory(prefix="browser-agent-decision-") as directory:
            root = Path(directory)
            schema_file = root / "schema.json"
            output_file = root / "response.json"
            await asyncio.to_thread(schema_file.write_text, json.dumps(schema), encoding="utf-8")
            args = [
                *self.command,
                "exec",
                "--ignore-user-config",
                "--ephemeral",
                "--skip-git-repo-check",
                "--sandbox",
                "read-only",
                "--cd",
                directory,
                "--model",
                self.model,
                "--config",
                'model_reasoning_effort="low"',
                "--config",
                'web_search="disabled"',
                "--output-schema",
                str(schema_file),
                "--output-last-message",
                str(output_file),
                "--color",
                "never",
            ]
            for feature in (
                "shell_tool",
                "unified_exec",
                "apps",
                "plugins",
                "hooks",
                "multi_agent",
                "multi_agent_v2",
                "browser_use",
                "browser_use_external",
                "computer_use",
                "in_app_browser",
                "image_generation",
                "imagegenext",
                "workspace_dependencies",
                "memories",
                "goals",
                "code_mode",
                "code_mode_only",
            ):
                args.extend(["--disable", feature])
            args.append("-")
            try:
                process = await asyncio.create_subprocess_exec(
                    *args,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
            except OSError:
                raise ProviderError("Cannot start Codex CLI. Check its installation.") from None
            try:
                await asyncio.wait_for(process.communicate(prompt.encode("utf-8")), self.timeout)
            except asyncio.CancelledError:
                process.kill()
                await process.wait()
                raise
            except TimeoutError:
                process.kill()
                await process.wait()
                raise ProviderError(
                    "Codex decision timed out or was cancelled; retry the task."
                ) from None
            if process.returncode != 0 or not output_file.is_file():
                raise ProviderError(
                    "Codex CLI failed. Check codex login status, model access and usage limits."
                )
            try:
                data = json.loads(await asyncio.to_thread(output_file.read_text, encoding="utf-8"))
            except (OSError, ValueError):
                raise InvalidDecision("Codex returned no valid structured response") from None
            logger.info("LLM codex latency=%.2fs", time.monotonic() - started)
            return data

    async def decide(self, context: str) -> Action:
        data = await self._request(
            SYSTEM_PROMPT + "\nYou are a data-only decision engine here. "
            "Do not use any CLI tools, files or shell. "
            "Return the next browser action as JSON matching the response schema.\nTools:\n"
            + json.dumps(DESCRIPTIONS)
            + "\nBROWSER TASK STATE:\n"
            + context,
            action_schema(),
        )
        try:
            action = data["action"]
            return Action.parse(action["name"], json.dumps(action["arguments"], ensure_ascii=False))
        except (KeyError, TypeError, ValueError, ValidationError):
            raise InvalidDecision(
                "Codex response did not match the browser action schema"
            ) from None

    async def verify(self, context: str, proposal: str) -> Verification:
        data = await self._request(
            VERIFIER_PROMPT.replace(
                "Use only the verification function.", "Return the verification JSON."
            )
            + "\nDo not use any CLI tools, files or shell.\n"
            + context
            + "\nUNPROVEN PROPOSAL:\n"
            + proposal,
            Verification.model_json_schema(),
        )
        try:
            return Verification.model_validate(data)
        except ValidationError:
            raise InvalidDecision("Invalid Codex verification response") from None
