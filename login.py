"""Login helper for the PM2020 backend.

This module keeps the login behavior small and reusable.  It uses the stable
ASP.NET control IDs found in Login.aspx:

    #txtUserName
    #txtPassword
    #btnLogin

Credentials may be supplied in creds.json:

    {
      "username": "your_username",
      "password": "your_password"
    }

or via environment variables:

    PM2020_USERNAME=your_username
    PM2020_PASSWORD=your_password
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

DEFAULT_LOGIN_URL = "https://pm2020.preferredparking.com:2020/Login.aspx"
DEFAULT_CREDS_PATH = Path(__file__).with_name("creds.json")

USERNAME_SELECTOR = "#txtUserName"
PASSWORD_SELECTOR = "#txtPassword"
LOGIN_BUTTON_SELECTOR = "#btnLogin"


@dataclass(frozen=True)
class Credentials:
    username: str
    password: str


def _read_json(path: Path) -> dict[str, Any]:
    """Read a JSON object from path, allowing an empty/missing creds file."""
    if not path.exists():
        return {}

    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        return {}

    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object.")
    return data


def load_credentials(creds_path: str | Path = DEFAULT_CREDS_PATH) -> Credentials:
    """Load credentials from creds.json, with environment-variable fallback."""
    path = Path(creds_path)
    data = _read_json(path)

    username = (
        data.get("username")
        or data.get("user")
        or data.get("PM2020_USERNAME")
        or os.getenv("PM2020_USERNAME")
    )
    password = (
        data.get("password")
        or data.get("pass")
        or data.get("PM2020_PASSWORD")
        or os.getenv("PM2020_PASSWORD")
    )

    if not username or not password:
        raise ValueError(
            "Missing PM2020 credentials. Add username/password to creds.json "
            "or set PM2020_USERNAME and PM2020_PASSWORD."
        )

    return Credentials(username=str(username), password=str(password))


def login_to_pm2020(
    page: Page,
    *,
    creds_path: str | Path = DEFAULT_CREDS_PATH,
    login_url: str = DEFAULT_LOGIN_URL,
    timeout_ms: int = 30_000,
) -> str:
    """Navigate to PM2020, fill credentials, click Login, and return final URL."""
    credentials = load_credentials(creds_path)

    page.goto(login_url, wait_until="domcontentloaded", timeout=timeout_ms)

    page.locator(USERNAME_SELECTOR).wait_for(state="visible", timeout=timeout_ms)
    page.locator(USERNAME_SELECTOR).fill(credentials.username)
    page.locator(PASSWORD_SELECTOR).fill(credentials.password)

    login_button = page.locator(LOGIN_BUTTON_SELECTOR)
    login_button.wait_for(state="visible", timeout=timeout_ms)

    # Login.aspx uses an ASP.NET __doPostBack handler on the Login button.  A
    # click is preferable to direct form submission because it lets the page run
    # its own postback code and preserve hidden fields like __VIEWSTATE.
    try:
        with page.expect_navigation(wait_until="domcontentloaded", timeout=15_000):
            login_button.click()
    except PlaywrightTimeoutError:
        # Some ASP.NET postbacks do not produce a Playwright navigation event.
        # The click still happened; give the page a chance to settle.
        try:
            page.wait_for_load_state("networkidle", timeout=5_000)
        except PlaywrightTimeoutError:
            pass

    return page.url


def appears_to_still_be_login_page(page: Page) -> bool:
    """Best-effort check that the browser is still looking at the login form."""
    try:
        return page.locator(USERNAME_SELECTOR).is_visible(timeout=1_000) and page.locator(
            LOGIN_BUTTON_SELECTOR
        ).is_visible(timeout=1_000)
    except PlaywrightTimeoutError:
        return False
