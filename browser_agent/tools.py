"""Deterministic safety gate and execution; only explicit YES authorizes one pending action."""

import hashlib
from collections.abc import Awaitable, Callable

from playwright.async_api import Error

from .browser import BrowserController, StaleElementError
from .models import Action, Observation, ToolResult
from .safety import classify, confirmation_text

Ask = Callable[[str], Awaitable[str | None]]


class ToolExecutor:
    def __init__(
        self,
        browser: BrowserController,
        ask: Ask,
        mode: str = "conservative",
        dry_run: bool = False,
    ):
        self.browser = browser
        self.ask = ask
        self.mode = mode
        self.dry_run = dry_run

    async def _stamp(self, action: Action) -> str:
        page = self.browser.current_page()
        parts = [page.url]
        for frame in page.frames[:10]:
            # Local-only hash including form state; never logged or sent to LLM.
            parts.append(
                await frame.evaluate("""() => JSON.stringify([
                document.body?.innerText,
                Array.from(document.querySelectorAll('input,select,textarea')).map(e =>
                    [e.value,e.checked,e.disabled])])""")
            )
        if hasattr(action.arguments, "element_id"):
            target = await self.browser.target(action.arguments.element_id)
            parts.append(await target.evaluate("el => el.outerHTML"))
        return hashlib.sha256("\n".join(parts).encode()).hexdigest()

    async def execute(self, action: Action, observation: Observation) -> ToolResult:
        decision, reason = classify(action, observation, self.mode)
        if decision == "block":
            return ToolResult(ok=False, message=reason, error="PolicyBlocked")
        if self.dry_run:
            return ToolResult(
                ok=False, message="Dry run: action proposed but not executed", error="DryRun"
            )
        if decision == "confirm":
            try:
                stamp = await self._stamp(action)
                reply = await self.ask(confirmation_text(action, observation, reason))
                if reply is None:
                    return ToolResult(
                        ok=False, message="User input unavailable", error="NeedsInput"
                    )
                if reply.strip() != "YES":
                    return ToolResult(
                        ok=False, message="User denied action; do not repeat it", error="UserDenied"
                    )
                if stamp != await self._stamp(action):
                    return ToolResult(
                        ok=False,
                        message="Page changed during confirmation; re-observe",
                        error="StaleApproval",
                    )
            except (Error, StaleElementError):
                return ToolResult(
                    ok=False,
                    message="Page/target changed during confirmation",
                    error="StaleApproval",
                )
        return await self.browser.execute(action)
