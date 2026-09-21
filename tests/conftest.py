import json
import os
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from browser_agent.browser import BrowserController
from browser_agent.config import Settings
from browser_agent.models import Action


def action(name: str, **arguments) -> Action:
    return Action.parse(name, json.dumps(arguments))


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_):
        pass


@pytest.fixture(scope="session")
def fixture_server():
    handler = partial(QuietHandler, directory=str(Path(__file__).parent / "fixtures"))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


@pytest.fixture
async def browser(tmp_path):
    settings = Settings(
        headless=os.getenv("TEST_HEADFUL") != "1",
        profile_dir=tmp_path / "profile",
        action_timeout_ms=3000,
    )
    async with BrowserController(settings) as instance:
        yield instance
