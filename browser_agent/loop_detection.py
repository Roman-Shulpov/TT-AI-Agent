"""Detect repeated actions even though runtime IDs are regenerated on every observation."""

import hashlib
import json
from collections import deque
from typing import Literal

from .models import Action, Observation


class LoopDetector:
    def __init__(self) -> None:
        self.signatures: deque[str] = deque(maxlen=6)
        self.states: deque[str] = deque(maxlen=8)
        self.warned = False

    def check(self, action: Action, observation: Observation) -> Literal["ok", "replan", "stop"]:
        if action.name in {"ask_user", "finish", "record_fact"}:
            return "ok"
        args = action.arguments.model_dump()
        target_id = args.pop("element_id", None)
        args.pop("risk", None)
        target = observation.element(target_id) if target_id else None
        if target:
            args["target"] = target.model_dump(exclude={"id"})
        state = observation.fingerprint()
        signature = hashlib.sha256(
            json.dumps([action.name, args, state], sort_keys=True).encode()
        ).hexdigest()
        self.signatures.append(signature)
        self.states.append(state)
        looping = self.signatures.count(signature) >= 3 or (
            len(self.states) == 8 and len(set(self.states)) == 1
        )
        if looping:
            if self.warned:
                return "stop"
            self.warned = True
            self.signatures.clear()
            self.states.clear()
            return "replan"
        return "ok"
