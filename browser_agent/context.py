"""Bounded memory: recent detail, older receipts, and exact page quotations."""

import json
from collections import deque

from .models import Action, Observation, ToolResult


class ContextMemory:
    def __init__(self, goal: str, recent_limit: int = 6, autonomous: bool = False):
        if not goal.strip() or len(goal) > 6000:
            raise ValueError("Goal must contain 1–6000 characters")
        self.goal = goal
        self.autonomous = autonomous
        self.recent_limit = recent_limit
        self.recent: deque[dict] = deque()
        self.summary: deque[str] = deque(maxlen=12)
        self.facts: deque[dict] = deque(maxlen=12)
        self.answers: deque[str] = deque(maxlen=8)
        self.feedback = ""
        self.compacted = 0

    def record(self, action: Action, result: ToolResult, observation: Observation) -> None:
        target = observation.element(getattr(action.arguments, "element_id", ""))
        item = {
            "tool": action.name,
            "target": target.name[:120] if target else "",
            "url": observation.url[:500],
            "ok": result.ok,
            "result": result.message[:600],
        }
        # Do not retain typed text, credentials, raw arguments or raw DOM in action history.
        self.recent.append(item)
        if len(self.recent) > self.recent_limit:
            old = self.recent.popleft()
            self.summary.append(
                f"{old['tool']} {old['target']}: {'ok' if old['ok'] else 'failed'}; "
                f"{old['result'][:180]} ({old['url'][:160]})"
            )
            self.compacted += 1

    def remember(self, quote: str, observation: Observation) -> ToolResult:
        if quote not in observation.text:
            return ToolResult(ok=False, message="Quote must occur verbatim in current visible text")
        fact = {"quote": quote, "url": observation.url[:1000]}
        if fact not in self.facts:
            self.facts.append(fact)
        return ToolResult(ok=True, message="Exact page quotation saved with source URL")

    def build(self, observation: Observation, step: int) -> str:
        # The provider receives a fresh bounded input; no hidden previous_response_id history.
        page = observation.model_dump()
        page["url"] = page["url"][:2048]
        data = {
            "step": step,
            "older_action_receipts": list(self.summary),
            "recent_actions": list(self.recent),
            "untrusted_saved_page_quotes": list(self.facts),
            "untrusted_browser_observation": page,
            # Keep authoritative instructions after the potentially long page data.
            "progress": {"compacted_steps": self.compacted, "feedback": self.feedback[:1500]},
            "user_answers": list(self.answers),
            "user_goal": self.goal,
            "autonomous": self.autonomous,
        }
        encoded = json.dumps(data, ensure_ascii=False)
        # Characters are deterministic; actual token usage comes from the provider.
        if len(encoded) > 48000:
            page["warnings"].append("Context budget reached; some history/elements were omitted.")
        for values in [
            data["older_action_receipts"],
            data["recent_actions"],
            page["elements"],
            data["untrusted_saved_page_quotes"],
        ]:
            while len(encoded) > 48000 and values:
                if values is page["elements"]:
                    values.pop()
                else:
                    values.pop(0)
                encoded = json.dumps(data, ensure_ascii=False)
        while len(encoded) > 48000 and page["text"]:
            page["text"] = page["text"][: len(page["text"]) // 2]
            encoded = json.dumps(data, ensure_ascii=False)
        while len(encoded) > 48000 and page["tabs"]:
            page["tabs"].pop(next(iter(page["tabs"])))
            encoded = json.dumps(data, ensure_ascii=False)
        if len(encoded) > 48000:
            raise ValueError("User context exceeds the safe input budget")
        return json.dumps(data, ensure_ascii=False)
