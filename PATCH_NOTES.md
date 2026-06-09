# Regional template patch notes

This patch updates PM2020UpdateAllLots from the old Charlotte-only CSV contract to the regional master CSV template.

## New source of truth

```text
SCRIPT_VERSION = "2026-06-08-regional-template-v1"
DEFAULT_CSV_PATH = PROJECT_DIR / "PM2020_Locations_Information.csv"
```

## New required CSV headers

```text
Lot Name
Lot ID
Lot Title
Facility Highlights
Facility Overview
Address 1
Address 2
```

## New PM2020 fill allowlist

The script still clicks only the matched lot-name cell and the exact `#btnLotInfo` save button. It now fills exactly five fields:

| CSV column | PM2020 selector |
|---|---|
| `Lot Title` | `#ContentPlaceHolder1_txtDescription` |
| `Facility Highlights` | `#ContentPlaceHolder1_txtNotes` |
| `Facility Overview` | `#ContentPlaceHolder1_txtFacOverview` |
| `Address 1` | `#ContentPlaceHolder1_txtAddress` |
| `Address 2` | `#ContentPlaceHolder1_txtAddress2` |

`Lot Name` remains display/selection only. `Lot ID` remains the table-match and hidden-ID verification key.

## Smoke checks run

From the patched project folder:

```bash
python -m py_compile main.py login.py __main__.py __init__.py
python main.py --version
python main.py --list
python main.py --mode one --select row:2 --dry-run
python main.py --mode one --select id:506 --dry-run
python main.py --mode three --select row:2,row:3,row:4 --dry-run
```

The patch was not live-tested against PM2020. Before any real save, run at least one dry run, then a single non-headless `--mode one` test with `--keep-open` if you want to inspect the modal.
