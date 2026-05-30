module: main
purpose: Command-line entry point for PM2020 backend automation.

current_task:
  - Launch Chromium with Playwright.
  - Create a browser context with ignore_https_errors=True.
  - Call login_to_pm2020 from login.py.
  - Save storage_state.json for later authenticated backend tasks.

run_examples:
  - python main.py --keep-open
  - python main.py --headless
  - python main.py --slow-mo 250 --keep-open

next_steps:
  - Read the enriched lot spreadsheet.
  - Navigate to the lot/facility editor for each Parkmaster Lot Id.
  - Update PM2020 ADDR and PM2020 Facility Overview fields.
  - Add dry-run and per-row logging before writing data.
