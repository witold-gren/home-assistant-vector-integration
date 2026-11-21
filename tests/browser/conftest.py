"""Run the Lovelace card (vector-control-card) in Google Chrome (Playwright) against a fake `hass`.

Run separately from the integration tests (the Home Assistant pytest plugin owns the event loop):
    .venv/bin/python -m pytest tests/browser -p no:homeassistant -p no:cacheprovider
"""

from __future__ import annotations

from collections.abc import Iterator
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import shutil
import threading

import pytest

playwright_api = pytest.importorskip("playwright.sync_api")

ROOT = Path(__file__).resolve().parents[2]
PHONE_LANDSCAPE = {"width": 874, "height": 402}  # iPhone 16 Pro in landscape (CSS px)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations() -> None:
    """Overrides the Home Assistant autouse fixture from tests/conftest.py (no HA here)."""


@pytest.fixture(autouse=True)
def fast_reconnect() -> None:
    """Overrides the WebSocket client fixture from tests/conftest.py (no client here)."""


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        pass


@pytest.fixture(scope="session")
def base_url() -> Iterator[str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(_QuietHandler, directory=str(ROOT)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


@pytest.fixture(scope="session")
def browser():
    if not shutil.which("google-chrome") and not Path("/Applications/Google Chrome.app").exists():
        pytest.skip("Google Chrome not installed")
    with playwright_api.sync_playwright() as pw:
        instance = pw.chromium.launch(channel="chrome", headless=True)
        yield instance
        instance.close()


@pytest.fixture
def open_card(browser, base_url: str):
    """Open the harness; query: offline=1 (robot unavailable), stream=0 (add-on without stream),
    portrait=1 (phone held upright)."""
    pages = []

    def _open(query: str = "", viewport: dict[str, int] | None = None):
        page = browser.new_page(viewport=viewport or PHONE_LANDSCAPE)
        page.errors = []
        page.on("pageerror", lambda error: page.errors.append(str(error)))
        page.goto(f"{base_url}/tests/browser/harness.html?{query}")
        page.wait_for_function("window.cardReady === true")
        pages.append(page)
        return page

    yield _open
    for page in pages:
        assert page.errors == [], page.errors
        page.close()


@pytest.fixture
def page(open_card):
    return open_card()
