"""Playwright lifecycle and generic actions; no knowledge of a user's task or website."""

from pathlib import Path

from playwright.async_api import (
    BrowserContext,
    ElementHandle,
    Error,
    Page,
    Playwright,
    async_playwright,
)
from playwright.async_api import TimeoutError as PlaywrightTimeout

from .config import Settings
from .models import Action, Observation, ToolResult
from .observation import NODE_SIGNATURE, ObservationExtractor


class StaleElementError(Exception):
    pass


class BrowserController:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.profile_path = str(Path(settings.profile_dir).resolve())
        self.extractor = ObservationExtractor(settings.max_elements, settings.max_text_chars)
        self.runtime: Playwright | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None
        self.pages: dict[str, Page] = {}
        self.last_observation: Observation | None = None
        self.observation_page: Page | None = None

    async def __aenter__(self) -> "BrowserController":
        self.runtime = await async_playwright().start()
        try:
            self.context = await self.runtime.chromium.launch_persistent_context(
                user_data_dir=self.profile_path,
                headless=self.settings.headless,
                viewport={"width": 1280, "height": 900},
                accept_downloads=False,
            )
            self.context.set_default_timeout(self.settings.action_timeout_ms)
            self.context.set_default_navigation_timeout(self.settings.navigation_timeout_ms)
            self.context.on("page", self._register_page)
            for page in self.context.pages:
                self._register_page(page)
            if self.page is None:
                self._register_page(await self.context.new_page())
            return self
        except BaseException:
            await self.runtime.stop()
            raise

    def _register_page(self, page: Page) -> None:
        if page not in self.pages.values():
            self.pages[f"t{len(self.pages) + 1}"] = page
            # JS alerts cannot block the entire run or silently approve a confirmation.
            page.on("dialog", lambda dialog: dialog.dismiss())
        self.page = page

    def current_page(self) -> Page:
        if self.page is None or self.page.is_closed():
            self.page = next(
                (p for p in reversed(list(self.pages.values())) if not p.is_closed()), None
            )
        if self.page is None:
            raise StaleElementError("All browser tabs are closed")
        return self.page

    async def __aexit__(self, *_: object) -> None:
        try:
            await self.extractor.clear()
            if self.context:
                await self.context.close()
        finally:
            if self.runtime:
                await self.runtime.stop()

    async def observe(self) -> Observation:
        page = self.current_page()
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=3000)
        except PlaywrightTimeout:
            # A partially loaded page can still provide useful evidence.
            pass
        tabs = {key: p.url[:1000] for key, p in list(self.pages.items())[-10:] if not p.is_closed()}
        self.last_observation = await self.extractor.extract(page, tabs)
        self.observation_page = page
        return self.last_observation

    async def target(self, element_id: str) -> ElementHandle:
        handle = self.extractor.handles.get(element_id)
        if not handle or not self.last_observation:
            raise StaleElementError("Element ID is not in the current snapshot; observe again")
        if self.current_page() != self.observation_page:
            raise StaleElementError("Active tab changed after observation")
        if self.current_page().url != self.last_observation.url:
            raise StaleElementError("URL changed after observation; observe again")
        # Pinning a node deliberately avoids a locator silently retargeting a replacement.
        if not await handle.evaluate("el => el.isConnected"):
            raise StaleElementError("Element no longer exists; page state changed")
        if not await handle.is_visible():
            raise StaleElementError("Element is no longer visible")
        if await handle.evaluate(NODE_SIGNATURE) != self.extractor.signatures[element_id]:
            raise StaleElementError("Element meaning or state changed after observation")
        return handle

    async def execute(self, action: Action) -> ToolResult:
        try:
            page = self.current_page()
            args = action.arguments.model_dump()
            target = await self.target(args["element_id"]) if "element_id" in args else None
            match action.name:
                case "navigate":
                    await page.goto(args["url"], wait_until="domcontentloaded")
                case "click":
                    await target.click()
                case "type_text":
                    await target.fill(args["text"])
                case "select_option":
                    await target.select_option(value=args["value"])
                case "scroll":
                    dy = args["amount"] * (1 if args["direction"] == "down" else -1)
                    await page.evaluate("dy => window.scrollBy(0,dy)", dy)
                case "go_back":
                    await page.go_back(wait_until="domcontentloaded")
                case "wait":
                    # Only an explicit model-selected bounded wait, never the main sync mechanism.
                    await page.wait_for_timeout(args["milliseconds"])
                case "press_key":
                    await target.press(args["key"])
                case "switch_tab":
                    selected = self.pages.get(args["tab_id"])
                    if selected is None or selected.is_closed():
                        raise StaleElementError("Tab no longer exists")
                    self.page = selected
                    await selected.bring_to_front()
                case _:
                    raise ValueError("Not a browser tool")
            return ToolResult(
                ok=True, message="Action executed; inspect next observation for outcome"
            )
        except (Error, StaleElementError, ValueError) as exc:
            # Exception messages may contain filled secrets, locators or URL query tokens.
            message = (
                str(exc)
                if isinstance(exc, StaleElementError)
                else f"{type(exc).__name__}: action failed; re-observe and choose another action"
            )
            return ToolResult(ok=False, message=message, error=type(exc).__name__)
