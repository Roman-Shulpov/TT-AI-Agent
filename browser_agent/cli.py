"""CLI opens visible Chromium, accepts arbitrary goals, and supports manual login."""

import argparse
import asyncio
import sys

from playwright.async_api import Error
from pydantic import ValidationError

from .agent import Agent
from .browser import BrowserController
from .config import Settings
from .llm import ProviderError
from .logging_utils import setup_logging, terminal_text
from .providers import create_provider


async def prompt(question: str) -> str | None:
    try:
        answer = await asyncio.to_thread(input, terminal_text(question))
        return None if answer.strip().lower() == "/stop" else answer
    except EOFError:
        return None


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Autonomous browser agent: enter any natural-language goal"
    )
    result.add_argument("--task", help="Natural-language task; omitted: prompt in terminal")
    result.add_argument("--start-url", help="Optional initial HTTP(S) URL")
    result.add_argument("--record", metavar="DIR", help="Record real browser video to this folder")
    result.add_argument(
        "--headless", action="store_true", help="Hide Chromium (default is visible)"
    )
    result.add_argument(
        "--login", action="store_true", help="Open browser for manual login, no LLM required"
    )
    result.add_argument(
        "--check", action="store_true", help="Launch Chromium and inspect a page without LLM"
    )
    result.add_argument(
        "--dry-run",
        action="store_true",
        help="Ask model for next action, then stop before execution",
    )
    result.add_argument(
        "--close-on-finish", action="store_true", help="Close browser without final Enter prompt"
    )
    return result


async def run_cli(args: argparse.Namespace) -> int:
    settings = Settings.from_env()
    if args.headless:
        settings.headless = True
    if args.record:
        from pathlib import Path

        settings.record_video_dir = Path(args.record)
    if args.login and settings.headless:
        print("Manual login requires a visible browser; remove --headless / HEADLESS=true.")
        return 2
    if (
        settings.llm_provider == "openai"
        and not (args.login or args.check)
        and not settings.llm_api_key.get_secret_value()
    ):
        print(
            "No LLM_API_KEY. Copy .env.example to .env and add your key locally.\n"
            "Browser-only check: python -m browser_agent --check"
        )
        return 2
    run_id = setup_logging(settings.llm_api_key.get_secret_value())
    print(
        f"Browser Agent | Model: {settings.llm_model} | Max steps: {settings.max_steps}\n"
        f"Safety: {settings.safety_mode} | Run: {run_id} | /stop or Ctrl+C to stop"
    )
    async with BrowserController(settings) as browser:
        if args.start_url:
            from .models import Action, Navigate

            result = await browser.execute(
                Action(name="navigate", arguments=Navigate(url=args.start_url))
            )
            if not result.ok:
                print(result.message)
                return 2
        if args.login:
            await prompt("Войдите в аккаунт вручную в браузере. Затем нажмите Enter: ")
            return 0
        if args.check:
            observation = await browser.observe()
            print(
                f"Chromium OK | elements={len(observation.elements)} | "
                f"text_chars={len(observation.text)}"
            )
            if not args.close_on_finish and not settings.headless:
                await prompt("Enter — закрыть браузер: ")
            return 0
        goal = args.task or await prompt("Введите задачу:\n> ")
        if goal is None or not goal.strip():
            return 2
        provider = create_provider(settings)
        try:
            agent = Agent(
                browser,
                provider,
                prompt,
                settings.max_steps,
                settings.recent_history,
                settings.safety_mode,
                args.dry_run,
            )
            result = await agent.run(goal)
            print(
                terminal_text(f"\n{result.status.upper()} | steps={result.steps}\n{result.summary}")
            )
            if not args.close_on_finish and not settings.headless:
                await prompt("Enter — закрыть браузер: ")
            return 0 if result.status == "completed" else 2
        finally:
            await provider.close()


def main() -> None:
    try:
        code = asyncio.run(run_cli(parser().parse_args()))
    except KeyboardInterrupt:
        print("\nStopped by user.")
        code = 130
    except ProviderError as exc:
        print(terminal_text(str(exc)))
        code = 2
    except (ValidationError, ValueError):
        print(
            "Invalid configuration/task. Check .env and --start-url; values withheld for privacy."
        )
        code = 2
    except Error as exc:
        print(
            f"Browser error ({type(exc).__name__}). Run: python -m playwright install chromium\n"
            "If the profile is in use, close the other instance or set a different PROFILE_DIR."
        )
        code = 2
    sys.exit(code)
