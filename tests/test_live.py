"""Opt-in real paid API smoke test. Never replaced by a fake when credentials are missing."""

import os

import pytest

from browser_agent.agent import Agent
from browser_agent.config import Settings
from browser_agent.llm import OpenAIProvider


@pytest.mark.live
@pytest.mark.browser
@pytest.mark.skipif(
    os.getenv("RUN_LIVE_TESTS") != "1", reason="Set RUN_LIVE_TESTS=1; requires API key"
)
async def test_live_llm_autonomous_browser_goal(browser, fixture_server):
    settings = Settings.from_env()
    assert settings.llm_api_key.get_secret_value(), "Add LLM_API_KEY to .env locally"
    provider = OpenAIProvider(settings)

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
