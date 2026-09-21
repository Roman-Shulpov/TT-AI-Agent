import asyncio
import json
from pathlib import Path

import pytest

from browser_agent import codex_provider
from browser_agent.config import Settings
from browser_agent.llm import InvalidDecision, ProviderError


def mock_cli(monkeypatch, response, returncode=0):
    calls = []
    monkeypatch.setattr(codex_provider, "cli_command", lambda: ["codex-test"])

    async def spawn(*args, **kwargs):
        output = Path(args[args.index("--output-last-message") + 1])

        class Process:
            async def communicate(self, prompt):
                calls.append((args, kwargs, prompt.decode()))
                await asyncio.to_thread(output.write_text, json.dumps(response), encoding="utf-8")

        process = Process()
        process.returncode = returncode
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    return calls


async def test_codex_uses_stdin_schema_and_disabled_integrations(monkeypatch):
    calls = mock_cli(monkeypatch, {"action": {"name": "wait", "arguments": {"milliseconds": 100}}})
    provider = codex_provider.CodexProvider(Settings())
    assert (await provider.decide("untrusted $(shell text)")).name == "wait"
    args, kwargs, prompt = calls[0]
    assert "untrusted $(shell text)" in prompt
    assert all("untrusted" not in arg for arg in args)
    assert args[args.index("--sandbox") + 1] == "read-only"
    assert "--ignore-user-config" in args
    assert "--ephemeral" in args
    for feature in ("shell_tool", "apps", "plugins", "browser_use", "multi_agent"):
        assert args[args.index(feature) - 1] == "--disable"
    assert kwargs["stdin"] == asyncio.subprocess.PIPE


async def test_codex_invalid_action_is_not_executed(monkeypatch):
    mock_cli(monkeypatch, {"action": {"name": "shell", "arguments": {"command": "bad"}}})
    with pytest.raises(InvalidDecision):
        await codex_provider.CodexProvider(Settings()).decide("state")


async def test_codex_failure_is_actionable_and_sanitized(monkeypatch):
    mock_cli(monkeypatch, {"secret": "not for logs"}, returncode=1)
    with pytest.raises(ProviderError, match="login status") as failure:
        await codex_provider.CodexProvider(Settings()).decide("state")
    assert "not for logs" not in str(failure.value)


async def test_codex_verifier_uses_its_own_schema(monkeypatch):
    mock_cli(monkeypatch, {"complete": False, "evidence": "Empty cart", "feedback": "Continue"})
    result = await codex_provider.CodexProvider(Settings()).verify("page", "Done")
    assert result.complete is False


def test_missing_cli_has_installation_guidance(monkeypatch):
    monkeypatch.setattr(codex_provider.shutil, "which", lambda _: None)
    with pytest.raises(ProviderError, match="codex login"):
        codex_provider.cli_command()
