"""Operational logs omit page contents, task text, entered values and URL paths/queries."""

import logging
import re
from pathlib import Path
from uuid import uuid4


def terminal_text(value: str) -> str:
    # Do not let untrusted web text inject terminal escape sequences.
    return re.sub(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]", "", value)


class SafeFormatter(logging.Formatter):
    def __init__(self, secret: str):
        super().__init__("%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
        self.secret = secret

    def format(self, record: logging.LogRecord) -> str:
        result = terminal_text(super().format(record))
        return result.replace(self.secret, "[redacted]") if self.secret else result


def setup_logging(secret: str = "") -> str:
    run_id = uuid4().hex[:12]
    Path("logs").mkdir(exist_ok=True)
    root = logging.getLogger("browser_agent")
    root.setLevel(logging.INFO)
    root.propagate = False
    for existing in root.handlers[:]:
        existing.close()
        root.removeHandler(existing)
    for handler in [
        logging.StreamHandler(),
        logging.FileHandler(f"logs/{run_id}.log", encoding="utf-8"),
    ]:
        handler.setFormatter(SafeFormatter(secret))
        root.addHandler(handler)
    return run_id
