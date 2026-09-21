"""Public browser smoke tests, NOT evidence of autonomous LLM task completion."""

import os

import pytest

from tests.conftest import action

pytestmark = [
    pytest.mark.browser,
    pytest.mark.public,
    pytest.mark.skipif(os.getenv("RUN_PUBLIC_TESTS") != "1", reason="Set RUN_PUBLIC_TESTS=1"),
]


async def test_public_dynamic_todo_ui(browser):
    result = await browser.execute(action("navigate", url="https://demo.playwright.dev/todomvc/"))
    assert result.ok, result.message
    observation = await browser.observe()
    textbox = next(e for e in observation.elements if e.role == "textbox")
    assert (
        await browser.execute(
            action("type_text", element_id=textbox.id, text="Review browser agent")
        )
    ).ok
    observation = await browser.observe()
    textbox = next(e for e in observation.elements if e.role == "textbox")
    assert (
        await browser.execute(
            action("press_key", element_id=textbox.id, key="Enter", risk="reversible")
        )
    ).ok
    observation = await browser.observe()
    assert "Review browser agent" in observation.text
    checkbox = next(e for e in observation.elements if e.role == "checkbox")
    assert (await browser.execute(action("click", element_id=checkbox.id, risk="reversible"))).ok
    observation = await browser.observe()
    completed = next(e for e in observation.elements if e.name == "Completed")
    assert (await browser.execute(action("click", element_id=completed.id, risk="read_only"))).ok
    assert "Review browser agent" in (await browser.observe()).text


async def test_public_catalog_navigation(browser):
    result = await browser.execute(action("navigate", url="https://books.toscrape.com/"))
    assert result.ok, result.message
    observation = await browser.observe()
    category = next(e for e in observation.elements if e.name == "Travel")
    assert (await browser.execute(action("click", element_id=category.id, risk="read_only"))).ok
    observation = await browser.observe()
    assert "Travel" in observation.title
    # Choose an observed product link by its generic URL metadata, only in this external test.
    product = next(
        e
        for e in observation.elements
        if e.role == "link" and "../../../" in e.href and "/category/" not in e.href and e.name
    )
    assert (await browser.execute(action("click", element_id=product.id, risk="read_only"))).ok
    observation = await browser.observe()
    assert "Product Information" in observation.text or "In stock" in observation.text
