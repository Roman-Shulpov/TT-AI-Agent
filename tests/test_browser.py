import pytest

from browser_agent.tools import ToolExecutor
from tests.conftest import action

pytestmark = pytest.mark.browser


async def open_fixture(browser, fixture_server, page="catalog.html"):
    assert (await browser.execute(action("navigate", url=f"{fixture_server}/{page}"))).ok
    return await browser.observe()


def find(observation, name):
    return next(e.id for e in observation.elements if e.name == name)


async def test_snapshot_filters_secrets_hidden_and_offscreen(browser, fixture_server):
    observation = await open_fixture(browser, fixture_server)
    names = [e.name for e in observation.elements]
    assert "Find equipment" in names
    assert "Hidden danger" not in names
    assert "Below viewport" not in names
    assert "Invisible instructions" not in observation.text
    assert "secret-fixture-password" not in observation.model_dump_json()
    assert (await browser.execute(action("scroll", direction="down", amount=1500))).ok
    assert "Below viewport" in [e.name for e in (await browser.observe()).elements]


async def test_dynamic_search_and_stale_ids(browser, fixture_server):
    observation = await open_fixture(browser, fixture_server)
    old_id = find(observation, "Find equipment")
    assert (await browser.execute(action("type_text", element_id=old_id, text="backpack"))).ok
    observation = await browser.observe()
    assert not (await browser.execute(action("click", element_id=old_id, risk="read_only"))).ok
    assert (
        await browser.execute(
            action("click", element_id=find(observation, "Search"), risk="read_only")
        )
    ).ok
    observation = await browser.observe()
    assert "Light backpack" in observation.text
    assert (
        await browser.execute(
            action("click", element_id=find(observation, "Add item"), risk="reversible")
        )
    ).ok
    assert "Cart: Light backpack" in (await browser.observe()).text


async def test_removed_replaced_and_changed_nodes_fail_safely(browser, fixture_server):
    observation = await open_fixture(browser, fixture_server)
    eid = find(observation, "Search")
    await (
        browser.current_page()
        .get_by_role("button", name="Search", exact=True)
        .evaluate("el => el.replaceWith(el.cloneNode(true))")
    )
    assert not (await browser.execute(action("click", element_id=eid, risk="read_only"))).ok
    observation = await browser.observe()
    eid = find(observation, "Search")
    await (
        browser.current_page()
        .get_by_role("button", name="Search", exact=True)
        .evaluate("el => el.textContent='Pay now'")
    )
    assert not (await browser.execute(action("click", element_id=eid, risk="read_only"))).ok


async def test_forms_frames_shadow_and_new_tab(browser, fixture_server):
    observation = await open_fixture(browser, fixture_server, "form.html")
    select = next(e for e in observation.elements if e.tag == "select")
    assert any(o["value"] == "pickup" for o in select.options)
    assert (await browser.execute(action("select_option", element_id=select.id, value="pickup"))).ok
    observation = await browser.observe()
    assert (
        await browser.execute(
            action("click", element_id=find(observation, "Gift wrap"), risk="reversible")
        )
    ).ok
    observation = await browser.observe()
    assert next(e for e in observation.elements if e.name == "Gift wrap").checked
    assert find(observation, "Shadow control")
    assert find(observation, "Styled checkbox")
    assert (
        await browser.execute(
            action("click", element_id=find(observation, "Frame action"), risk="read_only")
        )
    ).ok
    observation = await browser.observe()
    assert "Frame updated" in observation.text
    async with browser.context.expect_page():
        assert (
            await browser.execute(
                action(
                    "click",
                    element_id=find(observation, "Open catalog in new tab"),
                    risk="read_only",
                )
            )
        ).ok
    observation = await browser.observe()
    assert len(observation.tabs) == 2
    assert observation.title == "Fixture catalog"
    assert (await browser.execute(action("switch_tab", tab_id="t1"))).ok
    assert (await browser.observe()).title == "Fixture form"


async def test_denial_no_side_effect_and_changed_approval(browser, fixture_server):
    observation = await open_fixture(browser, fixture_server, "form.html")
    send = action("click", element_id=find(observation, "Send application"), risk="sensitive")

    async def deny(_):
        return "no"

    executor = ToolExecutor(browser, deny)
    assert (await executor.execute(send, observation)).error == "UserDenied"
    assert "Not submitted" in await browser.current_page().inner_text("body")

    async def changed(_):
        await (
            browser.current_page().get_by_label("Name", exact=True).fill("Changed during approval")
        )
        return "YES"

    executor.ask = changed
    assert (await executor.execute(send, observation)).error == "StaleApproval"
    assert "Not submitted" in await browser.current_page().inner_text("body")


async def test_explicit_confirmation_executes_once(browser, fixture_server):
    observation = await open_fixture(browser, fixture_server, "form.html")

    async def approve(_):
        return "YES"

    executor = ToolExecutor(browser, approve)
    send = action("click", element_id=find(observation, "Send application"), risk="sensitive")
    assert (await executor.execute(send, observation)).ok
    assert "Submitted" in (await browser.observe()).text


async def test_confirmation_accepts_lowercase_yes(browser, fixture_server):
    observation = await open_fixture(browser, fixture_server, "form.html")

    async def approve(_):
        return "yes"

    executor = ToolExecutor(browser, approve)
    send = action("click", element_id=find(observation, "Send application"), risk="sensitive")
    assert (await executor.execute(send, observation)).ok
    assert "Submitted" in (await browser.observe()).text
