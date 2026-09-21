"""Record a real model run on public demo data. No browser workflow is scripted here.

This opt-in recorder saves visible page text and the user goal. Do not use it with
personal accounts, confidential tasks, or private pages.
"""

import argparse
import asyncio
import json
import time
from datetime import UTC, datetime
from pathlib import Path

from browser_agent.agent import Agent
from browser_agent.browser import BrowserController
from browser_agent.config import Settings
from browser_agent.logging_utils import setup_logging
from browser_agent.providers import create_provider


class RecordedProvider:
    def __init__(self, delegate):
        self.delegate = delegate
        self.decisions = []

    async def decide(self, context):
        action = await self.delegate.decide(context)
        self.decisions.append({"name": action.name, "arguments": action.arguments.model_dump()})
        return action

    async def verify(self, context, proposal):
        return await self.delegate.verify(context, proposal)

    async def close(self):
        await self.delegate.close()


async def run(args):
    output = Path(args.output)
    await asyncio.to_thread(output.mkdir, parents=True, exist_ok=False)
    settings = Settings.from_env()
    settings.headless = False
    settings.profile_dir = output / "profile"
    settings.record_video_dir = output / "video"
    settings.safety_mode = "balanced"
    setup_logging(settings.llm_api_key.get_secret_value())
    provider = RecordedProvider(create_provider(settings))

    async def no_input(question):
        print("INPUT REQUESTED:", question, flush=True)
        return None

    started = time.monotonic()
    try:
        async with BrowserController(settings) as browser:
            agent = Agent(browser, provider, no_input, settings.max_steps, safety_mode="balanced")
            result = await agent.run(args.task)
            observation = await browser.observe()
            await browser.current_page().screenshot(path=str(output / "final.png"))
            report = {
                "date_utc": datetime.now(UTC).isoformat(),
                "provider": settings.llm_provider,
                "model": settings.llm_model,
                "task": args.task,
                "elapsed_seconds": round(time.monotonic() - started, 2),
                "result": result.model_dump(),
                "compacted_steps": agent.memory.compacted,
                "final_observation": observation.model_dump(),
                "saved_quotes": list(agent.memory.facts),
                "human_interventions": 0,
                "model_decisions": provider.decisions,
            }
            (output / "result.json").write_text(
                json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            print(result.model_dump_json(), flush=True)
    finally:
        await provider.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", required=True)
    parser.add_argument("--output", required=True, help="New directory for public demo evidence")
    asyncio.run(run(parser.parse_args()))
