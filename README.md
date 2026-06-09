# PM2020UpdateAllLots

Playwright automation for updating selected PM2020 lot metadata from the regional master CSV template.

The current source of truth is `main.py`:

```text
SCRIPT_VERSION = "2026-06-08-regional-template-v1"
```

This version lets you select one, three, five, or all lots; reviews existing PM2020 text before overwriting allowlisted fields; supports manual OTP/IP authentication; and uses a safer SaveLots request-body rewrite while still clicking PM2020's real Lot Info Save button.

## What it updates

The script fills only these five PM2020 Lot Info fields:

| CSV column | PM2020 selector | Meaning |
|---|---|---|
| `Lot Title` | `#ContentPlaceHolder1_txtDescription` | Public/display title for the lot |
| `Facility Highlights` | `#ContentPlaceHolder1_txtNotes` | Facility highlights text |
| `Facility Overview` | `#ContentPlaceHolder1_txtFacOverview` | Marketing/location overview |
| `Address 1` | `#ContentPlaceHolder1_txtAddress` | Street address |
| `Address 2` | `#ContentPlaceHolder1_txtAddress2` | City/state/ZIP line |

`Lot Name` is used for display/selection. `Lot ID` is used to match the CSV row to PM2020. The automation does **not** fill PM2020's internal lot-name field.

## Critical safety guardrails

During the post-login lot-update workflow, the script is intentionally allowlisted.

Allowed post-login actions:

1. Click only the matched lot-name cell in `#tblLots`.
2. Fill only these five fields:
   - `#ContentPlaceHolder1_txtDescription`
   - `#ContentPlaceHolder1_txtNotes`
   - `#ContentPlaceHolder1_txtFacOverview`
   - `#ContentPlaceHolder1_txtAddress`
   - `#ContentPlaceHolder1_txtAddress2`
3. Click only the exact Lot Info Save button:

```html
<input type="button" id="btnLotInfo" class="btn btn-success" value="Save" onclick="saveLotsInfo();">
```

The script does **not** use or click search fields, search buttons, Add New, Cancel, Close, tabs, pagination buttons, map controls, photo controls, amenity controls, note/rules/space/rate controls, menus, profile controls, or undefined fields/buttons.

After each save, the script navigates back to `Lots.aspx` for the next lot instead of clicking Cancel or Close.

## How lots are matched

The CSV field `Lot ID` is the primary identifier.

On `https://pm2020.preferredparking.com:2020/Admin/Lots.aspx`, the lot list is inside `#tblLots`. PM2020 rows use an `onclick` handler like:

```html
<tr onclick="getLotDetails(507)">
```

The script matches the CSV `Lot ID` to `getLotDetails(<id>)`, clicks the matched lot-name cell, waits for the Lot Info modal `#dvLotForm`, and verifies the hidden lot ID before editing:

```text
#ContentPlaceHolder1_hdnLotID
```

If DataTables has not attached the matching row to the current DOM page, the script may draw the DataTables page containing that row without typing in search and without clicking pagination controls.

## Setup

Python 3.10 or newer is recommended.

```bash
python -m venv .venv
source .venv/bin/activate  # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m playwright install chromium
```

## Credentials

Credentials may be supplied in `creds.json`:

```json
{
  "username": "YOUR_USERNAME",
  "password": "YOUR_PASSWORD"
}
```

or through environment variables:

```bash
export PM2020_USERNAME="YOUR_USERNAME"
export PM2020_PASSWORD="YOUR_PASSWORD"
```

On Windows PowerShell:

```powershell
$env:PM2020_USERNAME = "YOUR_USERNAME"
$env:PM2020_PASSWORD = "YOUR_PASSWORD"
```

Do not commit real credentials. Keep `creds.json`, `storage_state.json`, and `logs/` out of version control.

## CSV input

By default, place this regional master CSV in the project directory:

```text
PM2020_Locations_Information.csv
```

You can use another file with `--csv`:

```bash
python main.py --csv /path/to/file.csv --list
```

Required CSV columns:

```text
Lot Name
Lot ID
Lot Title
Facility Highlights
Facility Overview
Address 1
Address 2
```

Rows with missing required update values are skipped unless you select them directly, in which case the script refuses to update until the CSV is fixed.

## Data hygiene before a full run

PM2020's native JavaScript save path is fragile because it hand-builds JSON-like AJAX payloads. This project includes a safer SaveLots request-body rewrite before clicking Save, but the safest data-side practice is still to remove straight apostrophes from CSV update values before a full run, especially in:

```text
Lot Title
Facility Highlights
Facility Overview
Address 1
Address 2
```

For example, avoid values like:

```text
Surface lot parking near Uptown's Third Ward.
```

Prefer removing or rephrasing the apostrophe:

```text
Surface lot parking near Uptown Third Ward.
```

## Login and OTP/IP authentication

The login flow uses the original PM2020 login selectors:

```text
#txtUserName
#txtPassword
#btnLogin
```

If PM2020 redirects to `IPAuthentication.aspx`, the script pauses so you can enter the OTP manually in the browser and click Submit yourself. The script does not type the OTP and does not click the OTP Submit button.

Default OTP wait:

```text
--otp-timeout-ms 300000
```

That is 5 minutes. If OTP is required while running with `--headless`, the script exits and asks you to rerun non-headless.

## Selection modes

Interactive mode:

```bash
python main.py
```

Interactive mode asks for:

```text
1, 3, 5, or all
```

CLI modes:

```bash
python main.py --mode one
python main.py --mode three
python main.py --mode five
python main.py --mode all
```

Supported selectors for `--select` and interactive prompts:

| Selector | Meaning |
|---|---|
| `row:2` | Spreadsheet/CSV row number, including the header row |
| `#1` | CSV data row index, excluding the header row |
| `id:412` | Lot ID |
| `CLT - 1016 W 5th` | Exact `Lot Name` |
| `1016 West 5th Street Lot` | Exact `Lot Title` |
| `1016 W. 5th St.` | Exact `Address 1` |
| `Charlotte, NC 28202` | Exact `Address 2` |

Examples:

```bash
python main.py --mode one --select id:412 --dry-run
python main.py --mode one --select id:412
python main.py --mode three --select row:2,row:3,row:4
python main.py --mode five --select row:2,row:3,row:4,row:5,row:6
python main.py --mode all
```

Before opening the browser, the script prints the selected rows and asks for a typed confirmation unless `--yes` is supplied:

| Run type | Required confirmation |
|---|---|
| Partial run: one, three, or five lots | `UPDATE` |
| Full CSV run: all lots | `UPDATE ALL` |

## Existing PM2020 text behavior

Before filling any of the five allowlisted fields, the script reads the current PM2020 values.

If an allowlisted field already has nonblank text and that text differs from the CSV value, the default behavior is to prompt:

```text
Use [n]ew CSV text, keep [o]ld PM2020 text, [s]kip this lot, or [a]bort?
```

Choices:

| Choice | Behavior |
|---|---|
| `new` / `n` | Overwrite that field with the CSV value |
| `old` / `o` | Keep the current PM2020 value and do not fill that field |
| `skip` / `s` | Skip the entire lot; do not fill fields and do not click Save |
| `abort` / `a` | Exit the run |

You can also choose a non-interactive policy:

```bash
python main.py --existing-field-policy prompt
python main.py --existing-field-policy new
python main.py --existing-field-policy old
python main.py --existing-field-policy skip
```

Default:

```text
--existing-field-policy prompt
```

If the chosen final values do not change any of the five allowlisted fields, the script skips the lot and does not click Save.

## Save behavior

The script still clicks PM2020's real Lot Info Save button, `#btnLotInfo`. It does not call arbitrary backend endpoints directly.

Immediately before the click, the script builds a JSON payload from the current form values, installs a one-time Playwright route for:

```text
Lots.aspx/SaveLots
```

and rewrites the outgoing request body as valid JSON. This is intended to avoid failures from PM2020's native JavaScript string-built payloads.

The script treats the save as failed unless:

1. `Lots.aspx/SaveLots` returns HTTP `200`, and
2. the response body contains a nonzero saved lot ID.

## Useful commands

Show the current script version:

```bash
python main.py --version
```

List all CSV rows without opening the browser:

```bash
python main.py --list
```

Dry-run one lot without opening the browser:

```bash
python main.py --mode one --select id:412 --dry-run
```

Run one selected lot:

```bash
python main.py --mode one --select id:412
```

Run three selected lots:

```bash
python main.py --mode three --select row:2,row:3,row:4
```

Run five selected lots:

```bash
python main.py --mode five --select row:2,row:3,row:4,row:5,row:6
```

Run all complete CSV rows:

```bash
python main.py --mode all
```

Skip the typed confirmation prompt:

```bash
python main.py --mode one --select id:412 --yes
```

Continue to the next selected lot after a row-level failure:

```bash
python main.py --mode five --select row:2,row:3,row:4,row:5,row:6 --continue-on-error
```

Keep the browser open after the run for inspection:

```bash
python main.py --mode one --select id:412 --keep-open
```

Slow browser actions for debugging:

```bash
python main.py --mode one --select id:412 --slow-mo 250
```

Run headlessly:

```bash
python main.py --headless
```

Run from the parent folder as a package:

```bash
python -m PM2020UpdateAllLots
```

## CLI option summary

| Option | Default | Purpose |
|---|---:|---|
| `--csv PATH` | `PM2020_Locations_Information.csv` | Use a different input CSV |
| `--mode interactive|one|three|five|all` | `interactive` | Choose update scope |
| `--select VALUE` | blank | Select specific lots for one/three/five modes |
| `--list` | off | Print CSV rows and exit |
| `--dry-run` | off | Load/select/confirm rows, then exit before browser launch |
| `--yes` | off | Skip typed `UPDATE` / `UPDATE ALL` confirmation |
| `--existing-field-policy prompt|new|old|skip` | `prompt` | Decide how to handle existing PM2020 text |
| `--creds PATH` | `creds.json` | Use a different credentials file |
| `--login-url URL` | PM2020 Login.aspx | Override login URL |
| `--lots-url URL` | PM2020 Lots.aspx | Override Lots admin URL |
| `--storage-state PATH` | `storage_state.json` | Save Playwright storage state path |
| `--headless` | off | Run browser headlessly |
| `--slow-mo MS` | `0` | Slow Playwright actions for debugging |
| `--wait-ms MS` | `500` | Extra wait after key Lots.aspx steps |
| `--timeout-ms MS` | `30000` | Default Playwright timeout |
| `--otp-timeout-ms MS` | `300000` | Manual OTP/IP-auth wait time |
| `--continue-on-error` | off | Continue after row-level failures |
| `--keep-open` | off | Leave browser open until Enter is pressed |

## Logs

Each browser run writes row-level CSV logs under:

```text
logs/
```

Log fields:

```text
csv_row_number
parkmaster_lot_id
lot_name
status
message
```

The `message` field includes the row-level status detail and, for successful saves, a summary of the `Lots.aspx/SaveLots` response.

## Troubleshooting

### Playwright browser missing

If Playwright is installed but Chromium is missing, run:

```bash
python -m playwright install chromium
```

### OTP required while headless

If PM2020 requires OTP/IP authentication, rerun without `--headless` so you can manually enter the OTP in the browser.

### Selected lot ID not found

Use:

```bash
python main.py --list
```

Confirm that the CSV row has the correct `Lot ID`. The script matches that value to PM2020's `getLotDetails(<id>)` row handler.

### Backend validation failure

If a lot fails with a backend validation issue, first test that same lot manually in PM2020 with no changes. If manual save fails too, it is likely an existing PM2020 data/site issue rather than an automation issue.

If manual save works but the script fails, inspect the generated log under `logs/` and review the `Lots.aspx/SaveLots` request/response details.

### Apostrophe-related save failure

Scrub straight apostrophes from the CSV update values and rerun the affected lot. Lot Title, Facility Highlights, and Facility Overview are the most likely columns to contain problematic text.

## Recommended local-only files

These files/directories should not be committed:

```text
creds.json
storage_state.json
logs/
__pycache__/
*.pyc
.venv/
```
