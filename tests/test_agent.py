import json

import pytest

from browser_agent.agent import Agent
from browser_agent.llm import InvalidDecision
from browser_agent.models import Verification
from tests.conftest import action


async def approve(_):
    return "YES"


class CatalogTestProvider:
    """Test-only policy. Production CLI never imports or selects this fixture provider."""

    def __init__(self):
        self.contexts = []
        self.verifications = 0

    async def decide(self, context):
        data = json.loads(context)
        self.contexts.append(data)
        obs = data["untrusted_browser_observation"]

        def eid(name):
            return next(e["id"] for e in obs["elements"] if e["name"] == name)

        if len(self.contexts) == 1:
            # An early incorrect finish must not be accepted by the controller.
            return action("finish", summary="Done", evidence="No evidence yet")
        if "Cart: Light backpack" in obs["text"]:
            if not data["untrusted_saved_page_quotes"]:
                return action("record_fact", quote="Cart: Light backpack, 40 credits")
            return action(
                "finish",
                summary="Backpack added to cart",
                evidence="Cart: Light backpack, 40 credits",
            )
        if "Available" in obs["text"]:
            return action("click", element_id=eid("Add item"), risk="reversible")
        search = next(e for e in obs["elements"] if e["name"] == "Find equipment")
        if search["value"] != "backpack":
            return action("type_text", element_id=search["id"], text="backpack")
        return action("click", element_id=eid("Search"), risk="read_only")

    async def verify(self, context, proposal):
        self.verifications += 1
        data = json.loads(context)
        complete = (
            "Cart: Light backpack, 40 credits" in data["untrusted_browser_observation"]["text"]
        )
        return Verification(
            complete=complete,
            evidence="Observed cart text",
            feedback="Inspect cart" if complete else "Cart is empty; continue task",
        )


@pytest.mark.browser
async def test_real_browser_loop_compaction_and_verifier_rejection(browser, fixture_server):
    await browser.execute(action("navigate", url=fixture_server + "/catalog.html"))
    provider = CatalogTestProvider()
    agent = Agent(browser, provider, approve, max_steps=12, recent_history=2)
    result = await agent.run("Find a backpack costing at most 50 and add it to cart")
    assert result.status == "completed"
    assert provider.verifications == 2
    assert len(provider.contexts) >= 6
    assert agent.memory.compacted > 0
    assert agent.memory.facts[0]["quote"] == "Cart: Light backpack, 40 credits"
    assert "Verifier rejected" in provider.contexts[1]["progress"]["feedback"]


class SingleProvider:
    def __init__(self, decision):
        self.decision = decision

    async def decide(self, context):
        return self.decision

    async def verify(self, context, proposal):
        return Verification(complete=False, evidence="Missing", feedback="Not complete")


@pytest.mark.browser
async def test_ask_user_unavailable_is_explicit_terminal_state(browser):
    async def no_input(_):
        return None

    result = await Agent(
        browser, SingleProvider(action("ask_user", question="Which website?")), no_input
    ).run("Find something")
    assert result.status == "needs_input"


@pytest.mark.browser
async def test_clarification_is_in_next_context(browser):
    class Provider(SingleProvider):
        async def decide(self, context):
            data = json.loads(context)
            if not data["user_answers"]:
                return action("ask_user", question="Which color?")
            assert data["user_answers"] == ["Blue"]
            return action("wait", milliseconds=100)

    async def answer(_):
        return "Blue"

    result = await Agent(browser, Provider(None), answer, max_steps=2).run("Choose a color")
    assert result.status == "stopped"
    assert result.steps == 2


@pytest.mark.browser
async def test_invalid_decisions_are_bounded(browser):
    class InvalidProvider(SingleProvider):
        async def decide(self, context):
            raise InvalidDecision("Invalid JSON")

    result = await Agent(browser, InvalidProvider(None), approve).run("Do something")
    assert result.status == "stopped"
    assert result.steps == 4


@pytest.mark.browser
async def test_dry_run_stops_before_navigation(browser):
    provider = SingleProvider(action("navigate", url="https://example.org/"))
    result = await Agent(browser, provider, approve, dry_run=True).run("Open example.org")
    assert result.status == "stopped"
    assert browser.current_page().url == "about:blank"
