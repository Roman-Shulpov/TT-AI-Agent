"""Opt-in real model smoke test: local Ollama or configured OpenAI."""

import os

import pytest

from browser_agent.agent import Agent
from browser_agent.config import Settings
from browser_agent.providers import create_provider


@pytest.mark.live
@pytest.mark.browser
@pytest.mark.skipif(
    os.getenv("RUN_LIVE_TESTS") != "1", reason="Set RUN_LIVE_TESTS=1; requires a running model"
)
async def test_live_llm_autonomous_browser_goal(browser, fixture_server):
    settings = Settings.from_env()
    if settings.llm_provider == "openai":
        assert settings.llm_api_key.get_secret_value(), "Add LLM_API_KEY to .env locally"
    provider = create_provider(settings)

    async def fixture_confirmation(_):
        # Only this isolated local fixture test can auto-approve. Never used by CLI.
        return "YES"

    try:
        result = await Agent(browser, provider, fixture_confirmation, max_steps=20).run(
            f"Open {fixture_server}/catalog.html. Find a backpack below 50 credits, "
            "add it to the cart and report its name and price. Do not submit any checkout form."
        )
        assert result.status == "completed", result.summary
        assert "Cart: Light backpack, 40 credits" in (await browser.observe()).text
    finally:
        await provider.close()
