"""
Saving one row per participant, to Google Sheets (or a local CSV for testing).

The sheet's first row is the header. New columns (e.g. after you add a question)
are appended to the header automatically; existing columns are never reordered,
so old rows stay aligned.

Google Sheets API calls per saved row
-------------------------------------
* Normal save:                         1  (append the row)
* First save after the app (re)starts: +2 to open the spreadsheet and worksheet
                                       (cached with st.cache_resource), +1 to
                                       read the header (cached in this process)
* Only if the header must change:      +1 to write it (+1 if the grid needs more columns)
* Only after a failed attempt:         +1 to check whether the row already exists

The header cache assumes nobody edits the header row by hand while the app is
running; after any failed attempt it is re-read.

Retries
-------
429 (quota) and 5xx errors and network errors are retried with exponential
backoff and jitter (MAX_ATTEMPTS attempts, waits of about 1, 2, 4, 8 s). Other
errors (e.g. 403 not shared, 404 wrong URL) fail immediately. Before appending
again after any failed attempt, including a retry the participant triggers with
the Continue button, the sheet is checked for a row with this participant_id, so
a write that succeeded but whose response was lost is never duplicated.
"""

import csv
import random
import threading
import time
from pathlib import Path

import streamlit as st

import survey_config as cfg

LOCAL_CSV = Path(__file__).parent / "data" / "responses.csv"
DEFAULT_WORKSHEET = "widget_game"
ID_COLUMN = "participant_id"

MAX_ATTEMPTS = 5
BACKOFF_BASE_SECONDS = 1.0  # waits ≈ 1, 2, 4, 8 s (× random 0.8–1.2) between the 5 attempts

# Serialises writes from concurrent sessions in this server process, so two
# participants finishing at once cannot race on the header or the CSV file.
# Held only during API calls, never while sleeping between retries.
_write_lock = threading.Lock()

# Process-wide caches (the module is imported once per server process).
_header_cache: list[str] | None = None  # current header row of the worksheet
_unconfirmed_ids: set[str] = set()  # IDs whose last save attempt failed (may or may not be in the sheet)

sleep = time.sleep  # indirection so tests can skip the waits


def sheets_configured() -> bool:
    try:
        return "gcp_service_account" in st.secrets and "gsheets" in st.secrets
    except Exception:  # no secrets.toml at all
        return False


@st.cache_resource(show_spinner=False)
def _client():
    import gspread

    return gspread.service_account_from_dict(dict(st.secrets["gcp_service_account"]))


@st.cache_resource(show_spinner=False)
def _worksheet():
    import gspread

    conf = st.secrets["gsheets"]
    ref = conf["spreadsheet"]
    client = _client()
    spreadsheet = client.open_by_url(ref) if ref.startswith("http") else client.open_by_key(ref)
    name = conf.get("worksheet", DEFAULT_WORKSHEET)
    try:
        return spreadsheet.worksheet(name)
    except gspread.WorksheetNotFound:
        return spreadsheet.add_worksheet(title=name, rows=1000, cols=200)


def _merge_header(existing: list[str], row: dict) -> list[str]:
    return existing + [k for k in row if k not in existing]


def _is_retryable(exc: Exception) -> bool:
    import gspread
    import requests

    if isinstance(exc, gspread.exceptions.APIError):
        code = exc.code if isinstance(exc.code, int) and exc.code > 0 else getattr(exc.response, "status_code", 0)
        return code == 429 or 500 <= code < 600
    return isinstance(exc, (requests.exceptions.ConnectionError, requests.exceptions.Timeout))


def _backoff_seconds(attempt: int) -> float:
    """Wait after failed attempt number `attempt` (0-based): base · 2^attempt with ±20 % jitter."""
    return BACKOFF_BASE_SECONDS * (2**attempt) * random.uniform(0.8, 1.2)


def _row_exists(ws, header: list[str], participant_id: str) -> bool:
    if ID_COLUMN not in header:
        return False
    column = ws.col_values(header.index(ID_COLUMN) + 1)
    return participant_id in column[1:]


def _save_to_sheet(row: dict, check_existing: bool) -> None:
    global _header_cache
    ws = _worksheet()
    if _header_cache is None:
        _header_cache = ws.row_values(1)
    header = _merge_header(_header_cache, row)
    if header != _header_cache:
        if len(header) > ws.col_count:  # a row has ~190 columns; widen the grid first
            ws.add_cols(len(header) - ws.col_count)
        ws.update(values=[header], range_name="A1")
        _header_cache = header
    if check_existing and _row_exists(ws, header, str(row[ID_COLUMN])):
        return  # an earlier attempt already wrote this row
    ws.append_row(
        [row.get(col, "") for col in header],
        value_input_option="RAW",
        insert_data_option="INSERT_ROWS",
        table_range="A1",
    )


def _save_to_sheet_with_retries(row: dict) -> None:
    global _header_cache
    pid = str(row[ID_COLUMN])
    for attempt in range(MAX_ATTEMPTS):
        try:
            with _write_lock:
                _save_to_sheet(row, check_existing=attempt > 0 or pid in _unconfirmed_ids)
            _unconfirmed_ids.discard(pid)
            return
        except Exception as exc:
            _unconfirmed_ids.add(pid)  # the append may have gone through; check before the next append
            _header_cache = None  # re-read the header next time in case it changed
            if not _is_retryable(exc) or attempt == MAX_ATTEMPTS - 1:
                raise
            wait = _backoff_seconds(attempt)
            print(f"[sheets] attempt {attempt + 1} failed for pid={pid} ({exc!r}); retrying in {wait:.1f}s")
            sleep(wait)


def _save_to_csv(row: dict) -> None:
    LOCAL_CSV.parent.mkdir(exist_ok=True)
    existing_rows: list[dict] = []
    existing_header: list[str] = []
    if LOCAL_CSV.exists():
        with LOCAL_CSV.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            existing_header = list(reader.fieldnames or [])
            existing_rows = list(reader)
    header = _merge_header(existing_header, row)
    with LOCAL_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=header)
        writer.writeheader()
        writer.writerows(existing_rows)
        writer.writerow(row)


def save_response(row: dict) -> str:
    """Save a participant's row. Returns where it was saved; raises on failure."""
    if sheets_configured():
        _save_to_sheet_with_retries(row)
        return "google_sheets"
    if cfg.ALLOW_LOCAL_CSV_FALLBACK:
        with _write_lock:
            _save_to_csv(row)
        return "local_csv"
    raise RuntimeError("Google Sheets is not configured and the local CSV fallback is disabled.")
