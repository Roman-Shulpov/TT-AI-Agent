"""Observe → decide → validate → execute, with an independent completion verifier."""

import logging
import time
from urllib.parse import urlsplit

from playwright.async_api import Error

from .browser import BrowserController, StaleElementError
from .context import ContextMemory
from .llm import DecisionProvider, InvalidDecision, ProviderError
from .loop_detection import LoopDetector
from .models import RunResult, ToolResult
from .tools import Ask, ToolExecutor

logger = logging.getLogger(__name__)


class Agent:
    def __init__(
        self,
        browser: BrowserController,
        provider: DecisionProvider,
        ask: Ask,
        max_steps: int = 30,
        recent_history: int = 6,
        safety_mode: str = "conservative",
        dry_run: bool = False,
    ):
        self.browser = browser
        self.provider = provider
        self.ask = ask
        self.max_steps = max_steps
        self.recent_history = recent_history
        self.executor = ToolExecutor(browser, ask, safety_mode, dry_run)
        self.memory: ContextMemory | None = None

    async def run(self, goal: str) -> RunResult:
        memory = self.memory = ContextMemory(goal, self.recent_history)
        detector = LoopDetector()
        errors = 0
        verification_failures = 0
        for step in range(1, self.max_steps + 1):
            started = time.monotonic()
            try:
                observation = await self.browser.observe()
                logger.info(
                    "STEP %s host=%s memory_compacted=%s",
                    step,
                    urlsplit(observation.url).hostname or "blank",
                    memory.compacted,
                )
                action = await self.provider.decide(memory.build(observation, step))
                logger.info(
                    "ACTION %s target=%s", action.name, getattr(action.arguments, "element_id", "-")
                )
                loop_state = detector.check(action, observation)
                if loop_state == "stop":
                    return RunResult(
                        status="stopped", summary="Repeated loop after replanning", steps=step
                    )
                if loop_state == "replan":
                    memory.feedback = (
                        "Loop detected: no progress. Replan; choose a different action."
                    )
                    logger.warning(memory.feedback)
                    continue
                if action.name == "finish":
                    # Re-observe after the actor's request, not from its own completion claim.
                    fresh = await self.browser.observe()
                    check = await self.provider.verify(
                        memory.build(fresh, step), action.arguments.model_dump_json()
                    )
                    if check.complete:
                        logger.info("VERIFIER accepted completion")
                        return RunResult(
                            status="completed", summary=action.arguments.summary, steps=step
                        )
                    verification_failures += 1
                    memory.feedback = "Verifier rejected completion: " + check.feedback
                    logger.warning("VERIFIER rejected completion; actor will replan")
                    if verification_failures >= 3:
                        return RunResult(
                            status="stopped", summary="Completion could not be verified", steps=step
                        )
                    continue
                if action.name == "ask_user":
                    answer = await self.ask(action.arguments.question + "\n> ")
                    if answer is None:
                        return RunResult(
                            status="needs_input", summary=action.arguments.question, steps=step
                        )
                    if not answer.strip():
                        memory.feedback = "User supplied no information; clarify what is necessary."
                        continue
                    memory.answers.append(answer[:1500])
                    result = ToolResult(ok=True, message="User supplied clarification")
                elif action.name == "record_fact":
                    result = memory.remember(action.arguments.quote, observation)
                else:
                    result = await self.executor.execute(action, observation)
                    if result.error == "NeedsInput":
                        return RunResult(
                            status="needs_input",
                            summary="Confirmation requires user input",
                            steps=step,
                        )
                    if result.error == "DryRun":
                        return RunResult(
                            status="stopped", summary=f"Dry run: proposed {action.name}", steps=step
                        )
                memory.record(action, result, observation)
                memory.feedback = "" if result.ok else result.message
                errors = 0 if result.ok else errors + 1
                logger.log(
                    logging.INFO if result.ok else logging.WARNING,
                    "RESULT %s error=%s elapsed=%.2fs",
                    "ok" if result.ok else "failed",
                    result.error or "-",
                    time.monotonic() - started,
                )
            except InvalidDecision as exc:
                errors += 1
                memory.feedback = str(exc)
                logger.warning("Invalid structured decision; re-observe and retry")
            except ProviderError as exc:
                logger.error("Stopping after provider failure")
                return RunResult(status="stopped", summary=str(exc), steps=step)
            except (Error, StaleElementError) as exc:
                errors += 1
                memory.feedback = f"Browser observation failed: {type(exc).__name__}; re-observe"
                logger.warning("Browser observation unavailable: %s", type(exc).__name__)
            if errors >= 4:
                logger.error("Stopping after four consecutive errors")
                return RunResult(
                    status="stopped",
                    summary="Four consecutive errors; safe retry limit",
                    steps=step,
                )
        return RunResult(
            status="stopped", summary="Maximum step budget reached", steps=self.max_steps
        )
