# PM2020UpdateAllLots

Playwright automation for updating selected PM2020 lot metadata from a CSV export.

## What it updates

The script updates only these Lot Info fields:

| CSV column | PM2020 selector |
|---|---|
| `PM2020 ADDR` | `#ContentPlaceHolder1_txtAddress` |
| `PM2020 Facility Overview` | `#ContentPlaceHolder1_txtFacOverview` |
| `PM2020 Facility Highlights` | `#ContentPlaceHolder1_txtNotes` |

## Critical safety guardrails

During the post-login lot-update workflow, the script is intentionally allowlisted:

- It clicks only the matched lot-name cell in `#tblLots`.
- It clicks only the exact Save button `#btnLotInfo` after verifying:
  - `type="button"`
  - `id="btnLotInfo"`
  - `value="Save"`
  - `onclick="saveLotsInfo();"`
- It fills only the three selectors listed above.
- It does **not** use the search field, search button, Add New, Cancel, Close, tabs, pagination buttons, map/photo/amenity/note/rules/space/rate controls, menus, or any undefined fields.
- After saving each lot, it navigates back to `Lots.aspx` for the next lot instead of clicking Cancel or Close.

The login flow still uses the Login page selectors from the original scaffold: `#txtUserName`, `#txtPassword`, and `#btnLogin`.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate  # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m playwright install chromium
```

## Credentials

Fill `creds.json`:

```json
{
  "username": "YOUR_USERNAME",
  "password": "YOUR_PASSWORD"
}
```

or set environment variables:

```bash
export PM2020_USERNAME="YOUR_USERNAME"
export PM2020_PASSWORD="YOUR_PASSWORD"
```

## CSV input

Place this CSV in the project directory unless you pass `--csv`:

```text
PM_Surface_Lots_Image_Audit_PM2020_Facility_Overview.csv
```

Required CSV columns:

```text
Lot Name
Description
Parkmaster Lot Id
PM2020 ADDR
PM2020 Facility Overview
PM2020 Facility Highlights
```

## First test run: choose 1 or 5 lots

From inside the project folder:

```bash
python main.py
```

The script asks whether to select `1`, `5`, or `all` lots. For testing, choose `1` or `5`.

You can select by CSV/spreadsheet row number, CSV data row, Parkmaster Lot Id, exact Lot Name, or exact PM2020 address:

```text
row:2
#1
id:412
CLT - 1016 W 5th
1016 W. 5th St.
```

For a five-lot test:

```text
row:2,row:3,row:4,row:5,row:6
```

Before opening the browser, the script prints the selected rows and requires you to type `UPDATE` for one/five lots or `UPDATE ALL` for the full sheet.

## Useful commands

List all CSV rows without opening the browser:

```bash
python main.py --list
```

Dry-run a selection without opening the browser:

```bash
python main.py --mode one --select id:412 --dry-run
```

Run one selected lot:

```bash
python main.py --mode one --select id:412
```

Run five selected lots:

```bash
python main.py --mode five --select row:2,row:3,row:4,row:5,row:6
```

Run the full CSV after you are comfortable:

```bash
python main.py --mode all
```

Run from the parent folder:

```bash
python -m PM2020UpdateAllLots
```

For debugging, keep the browser open after the run:

```bash
python main.py --mode one --select id:412 --keep-open --slow-mo 250
```

Run headlessly:

```bash
python main.py --headless
```

## Logs

Each browser run writes a row-level CSV log under:

```text
logs/
```

The log records the CSV row, Parkmaster Lot Id, lot name, status, and the observed `Lots.aspx/SaveLots` response summary.
