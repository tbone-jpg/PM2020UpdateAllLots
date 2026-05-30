"""PM2020 Playwright automation entry point.

First milestone: open Login.aspx, fill the username/password, and click Login.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from playwright.sync_api import sync_playwright

from login import DEFAULT_CREDS_PATH, DEFAULT_LOGIN_URL, appears_to_still_be_login_page, login_to_pm2020

DEFAULT_STORAGE_STATE_PATH = Path(__file__).with_name("storage_state.json")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Log in to the PM2020 backend with Playwright.")
    parser.add_argument("--creds", default=str(DEFAULT_CREDS_PATH), help="Path to creds.json.")
    parser.add_argument("--login-url", default=DEFAULT_LOGIN_URL, help="PM2020 login URL.")
    parser.add_argument(
        "--storage-state",
        default=str(DEFAULT_STORAGE_STATE_PATH),
        help="Where to save Playwright storage state after login.",
    )
    parser.add_argument("--headless", action="store_true", help="Run browser headlessly.")
    parser.add_argument(
        "--slow-mo",
        type=int,
        default=0,
        help="Slow Playwright actions by this many milliseconds for debugging.",
    )
    parser.add_argument(
        "--keep-open",
        action="store_true",
        help="Keep the browser open until ENTER is pressed.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=args.headless, slow_mo=args.slow_mo)
        context = browser.new_context(ignore_https_errors=True)
        page = context.new_page()

        final_url = login_to_pm2020(page, creds_path=args.creds, login_url=args.login_url)
        context.storage_state(path=args.storage_state)

        print(f"Login click completed. Current URL: {final_url}")
        print(f"Saved storage state to: {args.storage_state}")

        if appears_to_still_be_login_page(page):
            print("Warning: the login form is still visible. Check credentials or any login error text.")

        if args.keep_open:
            input("Press ENTER to close the browser...")

        browser.close()


if __name__ == "__main__":
    main()
