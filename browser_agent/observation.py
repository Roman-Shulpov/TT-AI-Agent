"""Bounded viewport snapshot with pinned DOM-node identity across each decision."""

from importlib.resources import files

from playwright.async_api import ElementHandle, Error, Page

from .models import BrowserElement, Observation

EXTRACT = files("browser_agent").joinpath("extract.js").read_text(encoding="utf-8")
NODE_SIGNATURE = """el => JSON.stringify([el.tagName, el.innerText?.slice(0,1000),
    el.parentElement?.innerText?.slice(0,500),
    el.getAttribute('href'), el.getAttribute('aria-label'), el.getAttribute('aria-labelledby'),
    el.getAttribute('role'), el.type, el.disabled, el.value, el.checked])"""


class ObservationExtractor:
    def __init__(self, max_elements: int, max_text: int):
        self.max_elements = max_elements
        self.max_text = max_text
        self.generation = 0
        self.handles: dict[str, ElementHandle] = {}
        self.signatures: dict[str, str] = {}

    async def clear(self) -> None:
        for handle in self.handles.values():
            try:
                await handle.dispose()
            except Error:
                # Disposal may race a destroyed page execution context.
                continue
        self.handles.clear()
        self.signatures.clear()

    async def extract(self, page: Page, tabs: dict[str, str]) -> Observation:
        await self.clear()
        self.generation += 1
        snapshot_id = f"s{self.generation}"
        elements: list[BrowserElement] = []
        texts: list[str] = []
        warnings: list[str] = []
        remaining = self.max_text
        element_budget = 18000
        for index, frame in enumerate(page.frames[:10]):
            if len(elements) >= self.max_elements or remaining <= 0:
                warnings.append("Snapshot limit reached. Scroll to inspect more content.")
                break
            try:
                if frame != page.main_frame:
                    iframe = await frame.frame_element()
                    box = await iframe.bounding_box()
                    await iframe.dispose()
                    viewport = page.viewport_size or {"height": 900, "width": 1280}
                    if not box or box["y"] >= viewport["height"] or box["y"] + box["height"] <= 0:
                        continue
                bundle = await frame.evaluate_handle(
                    EXTRACT,
                    {
                        "maxElements": self.max_elements - len(elements),
                        "maxText": remaining,
                    },
                )
                data = await bundle.evaluate(
                    "b => ({meta:b.meta,text:b.text,truncated:b.truncated})"
                )
                node_array = await bundle.get_property("nodes")
                properties = await node_array.get_properties()
                for key, handle in properties.items():
                    node = handle.as_element()
                    if node is None:
                        await handle.dispose()
                        continue
                    eid = f"{snapshot_id}-e{len(elements) + 1}"
                    element = BrowserElement(
                        id=eid, frame=f"frame-{index}", **data["meta"][int(key)]
                    )
                    size = len(element.model_dump_json())
                    if size > element_budget:
                        await node.dispose()
                        if "Element character budget reached; scroll for more." not in warnings:
                            warnings.append("Element character budget reached; scroll for more.")
                        continue
                    element_budget -= size
                    self.handles[eid] = node
                    self.signatures[eid] = await node.evaluate(NODE_SIGNATURE)
                    elements.append(element)
                texts.append(f"[frame-{index}]\n" + data["text"])
                remaining -= len(data["text"]) + 20
                if data["truncated"]:
                    warnings.append(f"frame-{index}: viewport data truncated; scroll for more.")
                await node_array.dispose()
                await bundle.dispose()
            except Error as exc:
                warnings.append(f"frame-{index}: {type(exc).__name__}; observe again if needed.")
        return Observation(
            snapshot_id=snapshot_id,
            url=page.url,
            title=(await page.title())[:240],
            text="\n".join(texts)[: self.max_text],
            elements=elements,
            tabs=tabs,
            scroll_y=round(await page.evaluate("window.scrollY")),
            warnings=warnings,
        )
