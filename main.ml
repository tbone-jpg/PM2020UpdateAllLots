module: main
purpose: CSV-driven PM2020 lot metadata update runner.

current_task:
  - Read the enriched CSV from the project directory.
  - Prompt for 1, 5, or all complete CSV rows unless --mode is supplied.
  - Confirm selected rows before opening the browser.
  - Log in to PM2020.
  - For each selected lot, navigate to https://pm2020.preferredparking.com:2020/Admin/Lots.aspx.
  - Wait for #tblLots tbody tr[onclick*='getLotDetails'] and add a default 3000 ms safety wait.
  - Match the lot row primarily by Parkmaster Lot Id against getLotDetails(<id>).
  - Click only the matched lot-name cell in the lot list.
  - Fill only the three allowlisted Lot Info fields.
  - Click only the exact #btnLotInfo Save button after verifying id/type/value/onclick.
  - Navigate back to Lots.aspx for the next lot rather than clicking Cancel or Close.

csv_columns:
  Lot Name: displayed and usable as a selector in the prompt.
  Description: retained for human context.
  Parkmaster Lot Id: primary row match against getLotDetails(<id>).
  PM2020 ADDR: written to #ContentPlaceHolder1_txtAddress.
  PM2020 Facility Overview: written to #ContentPlaceHolder1_txtFacOverview.
  PM2020 Facility Highlights: written to #ContentPlaceHolder1_txtNotes.

safety_allowlist:
  lot_list_click:
    - matched first td / lot-name cell inside #tblLots tbody tr[onclick*='getLotDetails']
  save_click:
    - selector: '#btnLotInfo'
    - type: 'button'
    - value: 'Save'
    - onclick: 'saveLotsInfo();'
  fill_fields:
    - '#ContentPlaceHolder1_txtAddress'
    - '#ContentPlaceHolder1_txtFacOverview'
    - '#ContentPlaceHolder1_txtNotes'
  intentionally_not_used:
    - search field / search button
    - pagination buttons
    - add new button
    - cancel / close buttons
    - tabs
    - map / amenities / photos / notes / rules / space / rate buttons
    - any field not listed in fill_fields

supported_launch_forms:
  - python main.py
  - python main.py --list
  - python main.py --mode one --select id:412
  - python main.py --mode five --select row:2,row:3,row:4,row:5,row:6
  - python main.py --mode all
  - python -m PM2020UpdateAllLots

cli_options:
  --csv: override input CSV path
  --mode: interactive, one, five, or all
  --select: comma-separated row:<csv row>, #<data row>, id:<lotid>, exact Lot Name, or exact PM2020 ADDR
  --list / --list-csv: list CSV rows and exit
  --dry-run: select/confirm rows and exit before browser opens
  --yes: bypass typed UPDATE / UPDATE ALL confirmation
  --wait-ms: extra wait after key Lots.aspx steps; default 3000
  --creds: override creds.json path
  --login-url: override Login.aspx URL
  --lots-url: override Admin/Lots.aspx URL
  --storage-state: override storage_state.json output path
  --headless: run Chromium headlessly
  --slow-mo: slow Playwright actions for debugging
  --continue-on-error: keep going after a row-level failure
  --keep-open: pause for ENTER before closing browser
