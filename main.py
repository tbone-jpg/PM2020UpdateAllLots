"""PM2020 lot metadata updater.

Reads the enriched CSV, lets you choose one lot, five lots, or all lots, then
updates only the explicitly allowlisted Lot Info fields in PM2020.

Post-login safety contract:

* The only lot-list click is the matched lot-name cell in #tblLots.
* The only save click is the exact #btnLotInfo button with onclick="saveLotsInfo();".
* The only lot fields written are:
    - #ContentPlaceHolder1_txtAddress
    - #ContentPlaceHolder1_txtFacOverview
    - #ContentPlaceHolder1_txtNotes
* No search boxes, search buttons, Add New, Cancel, Close, tab, map, amenity,
  photo, notes, rules, space, rate, profile, or menu controls are clicked.
* After each lot save, the script navigates back to Lots.aspx for the next lot
  instead of clicking Cancel or Close.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Sequence

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

try:
    from .login import (
        DEFAULT_CREDS_PATH,
        DEFAULT_LOGIN_URL,
        appears_to_still_be_login_page,
        login_to_pm2020,
    )
except ImportError:
    from login import (  # type: ignore[no-redef]
        DEFAULT_CREDS_PATH,
        DEFAULT_LOGIN_URL,
        appears_to_still_be_login_page,
        login_to_pm2020,
    )

PROJECT_DIR = Path(__file__).resolve().parent
DEFAULT_CSV_PATH = PROJECT_DIR / "PM_Surface_Lots_Image_Audit_PM2020_Facility_Overview.csv"
DEFAULT_STORAGE_STATE_PATH = PROJECT_DIR / "storage_state.json"
DEFAULT_LOG_DIR = PROJECT_DIR / "logs"
DEFAULT_LOTS_URL = "https://pm2020.preferredparking.com:2020/Admin/Lots.aspx"

LOT_TABLE_SELECTOR = "#tblLots"
LOT_ROW_SELECTOR = "#tblLots tbody tr[onclick*='getLotDetails']"
LOT_MODAL_SELECTOR = "#dvLotForm"
HIDDEN_LOT_ID_SELECTOR = "#ContentPlaceHolder1_hdnLotID"
SAVE_BUTTON_SELECTOR = "#btnLotInfo"

ADDRESS_SELECTOR = "#ContentPlaceHolder1_txtAddress"
FACILITY_OVERVIEW_SELECTOR = "#ContentPlaceHolder1_txtFacOverview"
FACILITY_HIGHLIGHTS_SELECTOR = "#ContentPlaceHolder1_txtNotes"

ALLOWED_LOT_FILL_SELECTORS = {
    "PM2020 ADDR": ADDRESS_SELECTOR,
    "PM2020 Facility Overview": FACILITY_OVERVIEW_SELECTOR,
    "PM2020 Facility Highlights": FACILITY_HIGHLIGHTS_SELECTOR,
}
EXPECTED_SAVE_ONCLICK = "saveLotsInfo();"
GET_LOT_DETAILS_RE = re.compile(r"getLotDetails\s*\(\s*(\d+)\s*\)")

LIST_LOTS_SCRIPT = r"""
() => {
    const tableSelector = '#tblLots';
    function extractId(row) {
        const onclick = row && row.getAttribute ? (row.getAttribute('onclick') || '') : '';
        const match = onclick.match(/getLotDetails\s*\(\s*([0-9]+)\s*\)/);
        return match ? match[1] : null;
    }
    function rowInfo(row, source) {
        const cells = Array.from(row.querySelectorAll('td')).map(td => (td.innerText || '').trim());
        return {
            lotId: extractId(row),
            lotName: cells[0] || '',
            description: cells[1] || '',
            spaces: cells[2] || '',
            standardRate: cells[3] || '',
            onclick: row.getAttribute('onclick') || '',
            source
        };
    }

    const byId = new Map();
    Array.from(document.querySelectorAll(`${tableSelector} tbody tr[onclick]`)).forEach(row => {
        const info = rowInfo(row, 'dom');
        if (info.lotId) byId.set(info.lotId, info);
    });

    const $ = window.jQuery || window.$;
    if ($ && $.fn && $.fn.DataTable && $.fn.DataTable.isDataTable(tableSelector)) {
        const table = $(tableSelector).DataTable();
        table.rows({order: 'applied', search: 'applied'}).every(function () {
            const node = this.node();
            if (node) {
                const info = rowInfo(node, 'datatable');
                if (info.lotId && !byId.has(info.lotId)) byId.set(info.lotId, info);
            }
        });
    }
    return Array.from(byId.values());
}
"""

CLICK_LOT_NAME_BY_ID_SCRIPT = r"""
(lotId) => {
    const id = String(lotId).trim();
    const tableSelector = '#tblLots';

    function extractId(row) {
        const onclick = row && row.getAttribute ? (row.getAttribute('onclick') || '') : '';
        const match = onclick.match(/getLotDetails\s*\(\s*([0-9]+)\s*\)/);
        return match ? match[1] : null;
    }

    function rowText(row) {
        return Array.from(row.querySelectorAll('td')).map(td => (td.innerText || '').trim()).join(' | ');
    }

    function clickFirstCell(row, source) {
        if (!row) return {clicked: false, reason: 'No row node.'};
        const firstCell = row.querySelector('td');
        if (!firstCell) return {clicked: false, reason: 'Matched row has no first td cell.'};
        row.scrollIntoView({block: 'center', inline: 'nearest'});
        firstCell.click();
        return {
            clicked: true,
            source,
            lotId: id,
            lotName: firstCell.innerText.trim(),
            text: rowText(row),
            onclick: row.getAttribute('onclick') || ''
        };
    }

    // Safest path: click a row already attached to the DOM.
    const domRows = Array.from(document.querySelectorAll(`${tableSelector} tbody tr[onclick]`));
    let row = domRows.find(r => extractId(r) === id);
    if (row) return clickFirstCell(row, 'dom-row');

    // If DataTables has paged rows away, draw the page containing the row and click
    // the first cell. This does not type into search or click pagination/buttons.
    const $ = window.jQuery || window.$;
    if ($ && $.fn && $.fn.DataTable && $.fn.DataTable.isDataTable(tableSelector)) {
        const table = $(tableSelector).DataTable();
        const allIndexes = table.rows({order: 'applied', search: 'applied'}).indexes().toArray();
        let targetIndex = null;
        for (const idx of allIndexes) {
            const candidate = table.row(idx).node();
            if (candidate && extractId(candidate) === id) {
                targetIndex = idx;
                break;
            }
        }

        if (targetIndex !== null) {
            const pageInfo = table.page.info();
            if (pageInfo && pageInfo.length && pageInfo.length > 0) {
                const displayPosition = allIndexes.indexOf(targetIndex);
                if (displayPosition >= 0) {
                    table.page(Math.floor(displayPosition / pageInfo.length)).draw(false);
                }
            }
            row = table.row(targetIndex).node();
            if (row && document.body.contains(row)) return clickFirstCell(row, 'datatable-drawn-row');
            return {clicked: false, reason: 'DataTables row was found but was not attached after draw.', lotId: id};
        }
    }

    return {
        clicked: false,
        reason: `No #tblLots row found with onclick getLotDetails(${id}).`,
        visibleSample: domRows.slice(0, 10).map(r => ({id: extractId(r), text: rowText(r)}))
    };
}
"""


@dataclass(frozen=True)
class LotUpdate:
    csv_data_index: int  # 1-based data row, excluding header.
    csv_row_number: int  # spreadsheet/CSV line number, including header.
    lot_name: str
    description: str
    parkmaster_lot_id: str
    address: str
    facility_overview: str
    facility_highlights: str

    @property
    def is_complete(self) -> bool:
        return all(
            value.strip()
            for value in (
                self.lot_name,
                self.parkmaster_lot_id,
                self.address,
                self.facility_overview,
                self.facility_highlights,
            )
        )

    def missing_fields(self) -> list[str]:
        missing: list[str] = []
        if not self.lot_name.strip():
            missing.append("Lot Name")
        if not self.parkmaster_lot_id.strip():
            missing.append("Parkmaster Lot Id")
        if not self.address.strip():
            missing.append("PM2020 ADDR")
        if not self.facility_overview.strip():
            missing.append("PM2020 Facility Overview")
        if not self.facility_highlights.strip():
            missing.append("PM2020 Facility Highlights")
        return missing

    def display_key(self) -> str:
        return (
            f"CSV #{self.csv_data_index} / row {self.csv_row_number} | "
            f"ID {self.parkmaster_lot_id} | {self.lot_name} | {self.address}"
        )


@dataclass(frozen=True)
class UpdateResult:
    csv_row_number: int
    parkmaster_lot_id: str
    lot_name: str
    status: str
    message: str


def _normalized_header(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.strip().lower())


def _find_header(headers: Sequence[str], aliases: Iterable[str]) -> str:
    by_normalized = {_normalized_header(header): header for header in headers}
    for alias in aliases:
        key = _normalized_header(alias)
        if key in by_normalized:
            return by_normalized[key]
    raise ValueError(
        "Missing required CSV column. Tried aliases: " + ", ".join(repr(a) for a in aliases)
    )


def _cell(row: dict[str, str], header: str) -> str:
    value = row.get(header, "")
    return value.strip() if value is not None else ""


def load_lot_updates(csv_path: str | Path) -> list[LotUpdate]:
    path = Path(csv_path).expanduser()
    if not path.exists():
        raise FileNotFoundError(
            f"CSV file not found: {path}\n"
            f"Place the CSV in the project folder or pass --csv /path/to/file.csv."
        )

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError(f"CSV file has no header row: {path}")

        headers = reader.fieldnames
        h_lot_name = _find_header(headers, ["Lot Name"])
        h_description = _find_header(headers, ["Description"])
        h_lot_id = _find_header(headers, ["Parkmaster Lot Id", "Parkmaster Lot ID", "Lot Id", "Lot ID"])
        h_address = _find_header(headers, ["PM2020 ADDR", "PM2020 Address"])
        h_overview = _find_header(headers, ["PM2020 Facility Overview", "Facility Overview"])
        h_highlights = _find_header(
            headers,
            ["PM2020 Facility Highlights", "Facility Highlights", "PM2020 Highlights"],
        )

        lots: list[LotUpdate] = []
        for csv_row_number, row in enumerate(reader, start=2):
            if not row or not any((value or "").strip() for value in row.values()):
                continue
            lots.append(
                LotUpdate(
                    csv_data_index=csv_row_number - 1,
                    csv_row_number=csv_row_number,
                    lot_name=_cell(row, h_lot_name),
                    description=_cell(row, h_description),
                    parkmaster_lot_id=_cell(row, h_lot_id),
                    address=_cell(row, h_address),
                    facility_overview=_cell(row, h_overview),
                    facility_highlights=_cell(row, h_highlights),
                )
            )

    if not lots:
        raise ValueError(f"CSV contained no data rows: {path}")
    return lots


def complete_lots(lots: Sequence[LotUpdate]) -> list[LotUpdate]:
    return [lot for lot in lots if lot.is_complete]


def incomplete_lots(lots: Sequence[LotUpdate]) -> list[LotUpdate]:
    return [lot for lot in lots if not lot.is_complete]


def print_lots(lots: Sequence[LotUpdate], *, limit: int | None = None) -> None:
    shown = list(lots if limit is None else lots[:limit])
    if not shown:
        print("No lots to show.")
        return

    print("CSV # | Row | Parkmaster ID | Lot Name | PM2020 ADDR")
    print("-" * 104)
    for lot in shown:
        print(
            f"{lot.csv_data_index:>5} | {lot.csv_row_number:>3} | {lot.parkmaster_lot_id:<13} | "
            f"{lot.lot_name:<38.38} | {lot.address}"
        )
    if limit is not None and len(lots) > limit:
        print(f"... {len(lots) - limit} more lots not shown. Use --list to print all rows.")


def _split_selection_tokens(raw: str) -> list[str]:
    return [token.strip() for token in raw.split(",") if token.strip()]


def _single_match(label: str, matches: Sequence[LotUpdate]) -> LotUpdate:
    if not matches:
        raise ValueError(f"No CSV lot matched {label!r}.")
    if len(matches) > 1:
        options = "\n".join("  - " + lot.display_key() for lot in matches[:10])
        raise ValueError(
            f"Selection {label!r} matched multiple CSV lots. Use row:<csv row> or id:<lot id>.\n"
            + options
        )
    return matches[0]


def resolve_selection_token(lots: Sequence[LotUpdate], token: str) -> LotUpdate:
    raw = token.strip()
    lowered = raw.casefold()

    if lowered.startswith("row:"):
        row_number = lowered.split(":", 1)[1].strip()
        if not row_number.isdigit():
            raise ValueError(f"Invalid row selector {raw!r}; expected row:<number>.")
        return _single_match(raw, [lot for lot in lots if lot.csv_row_number == int(row_number)])

    if lowered.startswith("#"):
        data_index = lowered[1:].strip()
        if not data_index.isdigit():
            raise ValueError(f"Invalid CSV data-row selector {raw!r}; expected #<number>.")
        return _single_match(raw, [lot for lot in lots if lot.csv_data_index == int(data_index)])

    if lowered.startswith("id:"):
        lot_id = lowered.split(":", 1)[1].strip()
        return _single_match(raw, [lot for lot in lots if lot.parkmaster_lot_id == lot_id])

    if raw.isdigit():
        id_matches = [lot for lot in lots if lot.parkmaster_lot_id == raw]
        row_matches = [lot for lot in lots if lot.csv_row_number == int(raw)]
        data_index_matches = [lot for lot in lots if lot.csv_data_index == int(raw)]
        unique = {lot.csv_row_number: lot for lot in [*id_matches, *row_matches, *data_index_matches]}
        if len(unique) > 1:
            raise ValueError(
                f"Numeric selection {raw!r} is ambiguous. Use id:{raw}, row:{raw}, "
                f"or #{raw} to clarify."
            )
        if unique:
            return next(iter(unique.values()))
        raise ValueError(f"No CSV lot matched numeric selector {raw!r}.")

    exact_lot_name = [lot for lot in lots if lot.lot_name.casefold() == raw.casefold()]
    if exact_lot_name:
        return _single_match(raw, exact_lot_name)

    exact_address = [lot for lot in lots if lot.address.casefold() == raw.casefold()]
    if exact_address:
        return _single_match(raw, exact_address)

    raise ValueError(
        f"No CSV lot matched {raw!r}. Use row:<csv row>, #<CSV data row>, "
        "id:<Parkmaster Lot Id>, exact Lot Name, or exact PM2020 ADDR."
    )


def resolve_selection_tokens(lots: Sequence[LotUpdate], tokens: Sequence[str]) -> list[LotUpdate]:
    selected: list[LotUpdate] = []
    seen_rows: set[int] = set()
    for token in tokens:
        lot = resolve_selection_token(lots, token)
        if lot.csv_row_number in seen_rows:
            raise ValueError(f"Duplicate selection: {lot.display_key()}")
        selected.append(lot)
        seen_rows.add(lot.csv_row_number)
    return selected


def choose_lots_interactively(lots: Sequence[LotUpdate]) -> tuple[str, list[LotUpdate]]:
    complete = complete_lots(lots)
    if not complete:
        raise ValueError("No complete CSV rows are available to update.")

    print(f"Loaded {len(lots)} CSV rows. {len(complete)} have all required update values.")
    missing = incomplete_lots(lots)
    if missing:
        print(f"Skipping {len(missing)} incomplete rows unless you fix the CSV and rerun.")

    print("\nFirst few complete rows:")
    print_lots(complete, limit=15)

    while True:
        mode = input("\nChoose test size: 1, 5, or all: ").strip().lower()
        if mode in {"1", "one"}:
            raw = input(
                "Enter one selector as row:<csv row>, #<CSV data row>, id:<Parkmaster ID>, exact Lot Name, "
                "or press ENTER for the first complete row: "
            ).strip()
            return "one", [complete[0]] if not raw else resolve_selection_tokens(lots, [raw])
        if mode in {"5", "five"}:
            raw = input(
                "Enter five comma-separated selectors, or press ENTER for the first five complete rows: "
            ).strip()
            selected = complete[:5] if not raw else resolve_selection_tokens(lots, _split_selection_tokens(raw))
            if len(selected) != 5:
                raise ValueError(f"Expected exactly 5 selected lots, got {len(selected)}.")
            return "five", selected
        if mode in {"all", "a"}:
            return "all", complete
        print("Please enter 1, 5, or all.")


def choose_lots_from_args(
    lots: Sequence[LotUpdate], *, mode: str, raw_select: str | None
) -> tuple[str, list[LotUpdate]]:
    complete = complete_lots(lots)
    if mode == "interactive":
        return choose_lots_interactively(lots)

    tokens = _split_selection_tokens(raw_select or "")

    if mode == "one":
        selected = [complete[0]] if not tokens else resolve_selection_tokens(lots, tokens)
        if len(selected) != 1:
            raise ValueError(f"--mode one expects exactly 1 lot, got {len(selected)}.")
        return mode, selected

    if mode == "five":
        selected = complete[:5] if not tokens else resolve_selection_tokens(lots, tokens)
        if len(selected) != 5:
            raise ValueError(f"--mode five expects exactly 5 lots, got {len(selected)}.")
        return mode, selected

    if mode == "all":
        if tokens:
            raise ValueError("--mode all cannot be combined with --select.")
        return mode, complete

    raise ValueError(f"Unknown mode: {mode}")


def require_complete_selected_lots(selected: Sequence[LotUpdate]) -> None:
    incomplete_selected = [lot for lot in selected if not lot.is_complete]
    if incomplete_selected:
        lines = "\n".join(
            f"  - {lot.display_key()} missing {', '.join(lot.missing_fields())}"
            for lot in incomplete_selected
        )
        raise ValueError(
            "Selected lots include rows with missing required values. Fix the CSV before updating:\n"
            + lines
        )


def confirm_before_browser(mode: str, selected: Sequence[LotUpdate], *, assume_yes: bool, dry_run: bool) -> None:
    print("\nSelected lots:")
    print_lots(selected)
    print("\nFields that will be written:")
    for label, selector in ALLOWED_LOT_FILL_SELECTORS.items():
        print(f"  {selector} <= {label}")
    print("\nAllowed clicks during the post-login lot-update workflow:")
    print("  1. The matched lot-name cell in #tblLots")
    print(f"  2. {SAVE_BUTTON_SELECTOR} only after field values are filled")

    if dry_run:
        return
    if assume_yes:
        return

    phrase = "UPDATE ALL" if mode == "all" else "UPDATE"
    typed = input(f"\nType {phrase!r} to continue, or anything else to abort: ").strip()
    if typed != phrase:
        raise SystemExit("Aborted before opening the browser.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Read PM2020 lot-update values from CSV, select 1/5/all lots, and update "
            "only allowlisted Lot Info fields."
        )
    )
    parser.add_argument("--csv", default=str(DEFAULT_CSV_PATH), help="Path to input CSV.")
    parser.add_argument(
        "--mode",
        choices=["interactive", "one", "five", "all"],
        default="interactive",
        help="Selection mode. Default prompts for 1, 5, or all.",
    )
    parser.add_argument(
        "--select",
        default="",
        help=(
            "Comma-separated selections for --mode one/five. Use row:<csv row>, "
            "#<CSV data row>, id:<Parkmaster Lot Id>, exact Lot Name, or exact PM2020 ADDR."
        ),
    )
    parser.add_argument("--list", "--list-csv", action="store_true", help="List CSV rows and exit.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Load/select/confirm rows, then exit before opening the browser.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip the typed UPDATE / UPDATE ALL confirmation prompt.",
    )
    parser.add_argument("--creds", default=str(DEFAULT_CREDS_PATH), help="Path to creds.json.")
    parser.add_argument("--login-url", default=DEFAULT_LOGIN_URL, help="PM2020 login URL.")
    parser.add_argument("--lots-url", default=DEFAULT_LOTS_URL, help="PM2020 Lots admin URL.")
    parser.add_argument(
        "--storage-state",
        default=str(DEFAULT_STORAGE_STATE_PATH),
        help="Where to save Playwright storage state after the run.",
    )
    parser.add_argument("--headless", action="store_true", help="Run browser headlessly.")
    parser.add_argument(
        "--slow-mo",
        type=int,
        default=0,
        help="Slow Playwright actions by this many milliseconds for debugging.",
    )
    parser.add_argument(
        "--wait-ms",
        type=int,
        default=3_000,
        help="Extra wait after key Lots.aspx steps. Default: 3000 ms.",
    )
    parser.add_argument(
        "--timeout-ms",
        type=int,
        default=30_000,
        help="Default Playwright timeout in milliseconds.",
    )
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Continue to the next selected lot after a row-level failure.",
    )
    parser.add_argument(
        "--keep-open",
        action="store_true",
        help="Keep the browser open until ENTER is pressed after the run.",
    )
    return parser.parse_args()


def go_to_lots_admin(page: Page, lots_url: str, *, timeout_ms: int = 30_000) -> str:
    page.goto(lots_url, wait_until="domcontentloaded", timeout=timeout_ms)
    try:
        page.wait_for_load_state("networkidle", timeout=5_000)
    except PlaywrightTimeoutError:
        pass
    return page.url


def wait_for_lot_list(page: Page, *, wait_ms: int, timeout_ms: int) -> int:
    page.locator(LOT_ROW_SELECTOR).first.wait_for(state="attached", timeout=timeout_ms)
    page.wait_for_timeout(wait_ms)
    rows = list_lots_on_page(page)
    if not rows:
        raise RuntimeError("No lot rows were detected after waiting for #tblLots.")
    return len(rows)


def list_lots_on_page(page: Page) -> list[dict[str, Any]]:
    rows = page.evaluate(LIST_LOTS_SCRIPT)
    if not isinstance(rows, list):
        return []
    return rows


def assert_selected_lots_exist(page: Page, selected: Sequence[LotUpdate]) -> None:
    page_lots = list_lots_on_page(page)
    page_ids = {str(row.get("lotId", "")).strip() for row in page_lots}
    missing = [lot.parkmaster_lot_id for lot in selected if lot.parkmaster_lot_id not in page_ids]
    if missing:
        sample = ", ".join(sorted(list(page_ids))[:20])
        raise RuntimeError(
            "These selected CSV Parkmaster Lot Ids were not found in the PM2020 lot table; "
            f"no updates were written: {', '.join(missing)}. Sample page IDs: {sample}"
        )


def click_lot_name_by_id(page: Page, lot: LotUpdate, *, wait_ms: int, timeout_ms: int) -> dict[str, Any]:
    page.wait_for_timeout(wait_ms)
    result = page.evaluate(CLICK_LOT_NAME_BY_ID_SCRIPT, lot.parkmaster_lot_id)
    if not isinstance(result, dict) or not result.get("clicked"):
        raise RuntimeError(
            f"Could not click lot-name cell for {lot.display_key()}: "
            f"{json.dumps(result, ensure_ascii=False)}"
        )
    page.locator(LOT_MODAL_SELECTOR).wait_for(state="visible", timeout=timeout_ms)
    page.wait_for_timeout(wait_ms)
    return result


def wait_for_detail_form_ready(page: Page, lot: LotUpdate, *, wait_ms: int, timeout_ms: int) -> None:
    page.locator(LOT_MODAL_SELECTOR).wait_for(state="visible", timeout=timeout_ms)
    for selector in ALLOWED_LOT_FILL_SELECTORS.values():
        page.locator(selector).wait_for(state="visible", timeout=timeout_ms)

    try:
        page.wait_for_function(
            """
            ([selector, expected]) => {
                const element = document.querySelector(selector);
                return !!element && String(element.value || '') === String(expected);
            }
            """,
            arg=[HIDDEN_LOT_ID_SELECTOR, lot.parkmaster_lot_id],
            timeout=timeout_ms,
        )
    except PlaywrightTimeoutError as exc:
        current_value = page.locator(HIDDEN_LOT_ID_SELECTOR).input_value(timeout=2_000)
        raise RuntimeError(
            f"Lot detail form did not load the expected ID {lot.parkmaster_lot_id}; "
            f"current hidden lot ID is {current_value!r}. Refusing to edit."
        ) from exc

    page.wait_for_timeout(wait_ms)


def safe_fill_lot_field(page: Page, selector: str, value: str, *, label: str, wait_ms: int, timeout_ms: int) -> None:
    if selector not in ALLOWED_LOT_FILL_SELECTORS.values():
        raise RuntimeError(f"Refusing to fill non-allowlisted selector: {selector}")

    if value.strip() == "":
        raise RuntimeError(f"Refusing to write blank value for {label}.")

    locator = page.locator(selector)
    if locator.count() != 1:
        raise RuntimeError(f"Expected exactly one field for {label} at {selector}; found {locator.count()}.")
    locator.wait_for(state="visible", timeout=timeout_ms)

    page.wait_for_timeout(wait_ms)
    locator.fill(value, timeout=timeout_ms)

    actual = locator.input_value(timeout=timeout_ms)
    if actual != value:
        raise RuntimeError(
            f"After filling {label}, PM2020 field value did not match the CSV value.\n"
            f"Expected: {value!r}\nActual:   {actual!r}"
        )


def click_save_lot_info(page: Page, *, wait_ms: int, timeout_ms: int) -> tuple[int | None, str | None]:
    save_button = page.locator(SAVE_BUTTON_SELECTOR)
    if save_button.count() != 1:
        raise RuntimeError(f"Expected exactly one save button at {SAVE_BUTTON_SELECTOR}; found {save_button.count()}.")
    save_button.wait_for(state="visible", timeout=timeout_ms)

    attrs = save_button.evaluate(
        """
        el => ({
            type: el.getAttribute('type') || '',
            id: el.getAttribute('id') || '',
            value: el.getAttribute('value') || '',
            onclick: el.getAttribute('onclick') || '',
            disabled: !!el.disabled,
            hiddenClass: el.classList.contains('hidden'),
            display: window.getComputedStyle(el).display,
            visibility: window.getComputedStyle(el).visibility
        })
        """
    )
    if attrs.get("id") != "btnLotInfo":
        raise RuntimeError(f"Save button allowlist failed: unexpected id {attrs.get('id')!r}.")
    if str(attrs.get("type", "")).casefold() != "button":
        raise RuntimeError(f"Save button allowlist failed: unexpected type {attrs.get('type')!r}.")
    if attrs.get("value") != "Save":
        raise RuntimeError(f"Save button allowlist failed: unexpected value {attrs.get('value')!r}.")
    if attrs.get("onclick") != EXPECTED_SAVE_ONCLICK:
        raise RuntimeError(f"Save button allowlist failed: unexpected onclick {attrs.get('onclick')!r}.")
    if attrs.get("disabled") or attrs.get("hiddenClass") or attrs.get("display") == "none" or attrs.get("visibility") == "hidden":
        raise RuntimeError("Save button exists but is disabled/hidden; refusing to click.")

    page.wait_for_timeout(wait_ms)
    try:
        with page.expect_response(lambda response: "Lots.aspx/SaveLots" in response.url, timeout=timeout_ms) as response_info:
            save_button.click(timeout=timeout_ms)
        response = response_info.value
        body = None
        try:
            body = response.text()[:500]
        except Exception:
            body = None
        page.wait_for_timeout(wait_ms)
        return response.status, body
    except PlaywrightTimeoutError as exc:
        page.wait_for_timeout(wait_ms)
        raise RuntimeError("Timed out waiting for Lots.aspx/SaveLots after clicking #btnLotInfo.") from exc


def update_one_lot(page: Page, lot: LotUpdate, *, lots_url: str, wait_ms: int, timeout_ms: int) -> UpdateResult:
    current_url = go_to_lots_admin(page, lots_url, timeout_ms=timeout_ms)
    if appears_to_still_be_login_page(page):
        raise RuntimeError(f"Navigation to Lots.aspx returned to the login page. Current URL: {current_url}")

    row_count = wait_for_lot_list(page, wait_ms=wait_ms, timeout_ms=timeout_ms)
    print(f"Detected {row_count} lot row(s) in #tblLots/DataTables.")

    assert_selected_lots_exist(page, [lot])

    click_result = click_lot_name_by_id(page, lot, wait_ms=wait_ms, timeout_ms=timeout_ms)
    print(
        "Opened lot-name cell: "
        f"source={click_result.get('source')}, text={click_result.get('text')!r}"
    )

    wait_for_detail_form_ready(page, lot, wait_ms=wait_ms, timeout_ms=timeout_ms)

    safe_fill_lot_field(
        page,
        ADDRESS_SELECTOR,
        lot.address,
        label="PM2020 ADDR",
        wait_ms=wait_ms,
        timeout_ms=timeout_ms,
    )
    safe_fill_lot_field(
        page,
        FACILITY_OVERVIEW_SELECTOR,
        lot.facility_overview,
        label="PM2020 Facility Overview",
        wait_ms=wait_ms,
        timeout_ms=timeout_ms,
    )
    safe_fill_lot_field(
        page,
        FACILITY_HIGHLIGHTS_SELECTOR,
        lot.facility_highlights,
        label="PM2020 Facility Highlights",
        wait_ms=wait_ms,
        timeout_ms=timeout_ms,
    )

    status, body = click_save_lot_info(page, wait_ms=wait_ms, timeout_ms=timeout_ms)
    return UpdateResult(
        csv_row_number=lot.csv_row_number,
        parkmaster_lot_id=lot.parkmaster_lot_id,
        lot_name=lot.lot_name,
        status="saved",
        message=f"SaveLots response status={status}; body={body!r}",
    )


def write_run_log(results: Sequence[UpdateResult], *, log_dir: Path = DEFAULT_LOG_DIR) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / f"pm2020_lot_update_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["csv_row_number", "parkmaster_lot_id", "lot_name", "status", "message"],
        )
        writer.writeheader()
        for result in results:
            writer.writerow(
                {
                    "csv_row_number": result.csv_row_number,
                    "parkmaster_lot_id": result.parkmaster_lot_id,
                    "lot_name": result.lot_name,
                    "status": result.status,
                    "message": result.message,
                }
            )
    return path


def run_browser_updates(selected: Sequence[LotUpdate], args: argparse.Namespace) -> list[UpdateResult]:
    storage_state_path = Path(args.storage_state).expanduser()
    storage_state_path.parent.mkdir(parents=True, exist_ok=True)

    results: list[UpdateResult] = []
    browser = None
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=args.headless, slow_mo=args.slow_mo)
            context = browser.new_context(ignore_https_errors=True)
            page = context.new_page()

            login_url_after_click = login_to_pm2020(
                page,
                creds_path=args.creds,
                login_url=args.login_url,
                timeout_ms=args.timeout_ms,
            )
            print(f"Login click completed. Current URL: {login_url_after_click}")

            if appears_to_still_be_login_page(page):
                raise SystemExit(
                    "Login form is still visible after clicking Login. "
                    "Check credentials or any login error text before continuing."
                )

            context.storage_state(path=str(storage_state_path))
            print(f"Saved storage state to: {storage_state_path}")

            for index, lot in enumerate(selected, start=1):
                print(f"\n=== Updating {index} of {len(selected)} ===")
                print(lot.display_key())
                try:
                    result = update_one_lot(
                        page,
                        lot,
                        lots_url=args.lots_url,
                        wait_ms=args.wait_ms,
                        timeout_ms=args.timeout_ms,
                    )
                    results.append(result)
                    print(f"Status: {result.status}. {result.message}")
                    write_run_log(results)
                except Exception as exc:
                    failed = UpdateResult(
                        csv_row_number=lot.csv_row_number,
                        parkmaster_lot_id=lot.parkmaster_lot_id,
                        lot_name=lot.lot_name,
                        status="failed",
                        message=str(exc),
                    )
                    results.append(failed)
                    write_run_log(results)
                    print(f"ERROR on {lot.display_key()}: {exc}")
                    if not args.continue_on_error:
                        raise

            if results:
                log_path = write_run_log(results)
                print(f"\nWrote run log: {log_path}")

            if args.keep_open:
                input("Press ENTER to close the browser...")

            browser.close()
            browser = None
    except PlaywrightError as exc:
        message = str(exc)
        if "Executable doesn't exist" in message or "playwright install" in message.lower():
            raise SystemExit(
                "Playwright is installed, but the Chromium browser is missing. Run:\n"
                "    python -m playwright install chromium"
            ) from exc
        raise
    finally:
        if browser is not None and browser.is_connected():
            browser.close()
    return results


def main() -> None:
    args = parse_args()

    if args.wait_ms < 0:
        raise SystemExit("--wait-ms must be zero or greater.")

    lots = load_lot_updates(args.csv)
    if args.list:
        print_lots(lots)
        missing = incomplete_lots(lots)
        if missing:
            print("\nRows missing one or more required update values:")
            print_lots(missing)
        return

    mode, selected = choose_lots_from_args(lots, mode=args.mode, raw_select=args.select)
    require_complete_selected_lots(selected)
    confirm_before_browser(mode, selected, assume_yes=args.yes, dry_run=args.dry_run)

    if args.dry_run:
        print("\nDry run complete. Browser was not opened and PM2020 was not changed.")
        return

    run_browser_updates(selected, args)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        raise SystemExit("Interrupted by user.") from None
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
