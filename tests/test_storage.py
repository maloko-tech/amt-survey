"""Google Sheets saving with a mocked worksheet: API-call count, retries, no duplicates, no CSV leaks."""

import gspread
import pytest
import requests

import storage
import survey_config as cfg
from tests.test_app_flow import (  # noqa: F401  (env is a fixture)
    click, do_comprehension, do_consent, do_demographics, do_ec, do_instructions, env, page, play_game, start,
)


class FakeResponse:
    def __init__(self, code):
        self.status_code = code
        self.text = f"HTTP {code}"

    def json(self):
        return {"error": {"code": self.status_code, "message": f"fake {self.status_code}", "status": "FAKE"}}


def api_error(code: int) -> gspread.exceptions.APIError:
    return gspread.exceptions.APIError(FakeResponse(code))


APPENDED_THEN_LOST = "appended-then-lost"  # the row is written, but the response fails (e.g. timeout)


class FakeWorksheet:
    """Minimal stand-in for gspread.Worksheet that records every API call."""

    def __init__(self, append_failures=(), col_count=26):
        self.rows: list[list] = []
        self.col_count = col_count
        self.calls: list[str] = []
        self.append_failures = list(append_failures)

    def row_values(self, i):
        self.calls.append("row_values")
        return list(self.rows[0]) if self.rows else []

    def add_cols(self, n):
        self.calls.append("add_cols")
        self.col_count += n

    def update(self, values, range_name):
        self.calls.append("update")
        if self.rows:
            self.rows[0] = list(values[0])
        else:
            self.rows.append(list(values[0]))

    def col_values(self, c):
        self.calls.append("col_values")
        return [r[c - 1] if len(r) >= c else "" for r in self.rows]

    def append_row(self, values, **kwargs):
        self.calls.append("append_row")
        if self.append_failures:
            failure = self.append_failures.pop(0)
            if failure == APPENDED_THEN_LOST:
                self.rows.append(list(values))
                raise requests.exceptions.ConnectionError("response lost")
            raise failure
        self.rows.append(list(values))

    def ids(self):
        return [r[0] for r in self.rows[1:]]


@pytest.fixture
def sheet(tmp_path, monkeypatch):
    """Sheets 'configured' with a fake worksheet; CSV fallback off; no real waiting."""
    holder = {"ws": FakeWorksheet()}
    sleeps: list[float] = []
    monkeypatch.setattr(storage, "sheets_configured", lambda: True)
    monkeypatch.setattr(storage, "_worksheet", lambda: holder["ws"])
    monkeypatch.setattr(storage, "_header_cache", None)
    monkeypatch.setattr(storage, "_unconfirmed_ids", set())
    monkeypatch.setattr(storage, "sleep", sleeps.append)
    monkeypatch.setattr(storage, "LOCAL_CSV", tmp_path / "responses.csv")
    monkeypatch.setattr(cfg, "ALLOW_LOCAL_CSV_FALLBACK", False)

    def use(ws):
        holder["ws"] = ws
        return ws

    return use, sleeps


def row(pid="P001", **extra):
    return {"participant_id": pid, "sequence": "S1", "total_profit": 123, **extra}


def test_api_calls_per_save_are_minimal(sheet):
    use, _ = sheet
    ws = use(FakeWorksheet(col_count=2))
    storage.save_response(row("P001"))
    # First save into an empty tab: read header once, widen grid, write header, append.
    assert ws.calls == ["row_values", "add_cols", "update", "append_row"]
    ws.calls.clear()
    storage.save_response(row("P002"))
    assert ws.calls == ["append_row"]  # steady state: exactly one API call per participant
    ws.calls.clear()
    storage.save_response(row("P003", feedback="new column"))
    # Header only rewritten when it changes (the 3-column grid also needs a 4th column here).
    assert ws.calls == ["add_cols", "update", "append_row"]
    assert ws.ids() == ["P001", "P002", "P003"]


def test_429_then_success_writes_exactly_one_row(sheet):
    use, sleeps = sheet
    ws = use(FakeWorksheet(append_failures=[api_error(429)]))
    assert storage.save_response(row()) == "google_sheets"
    assert ws.ids() == ["P001"]
    assert len(sleeps) == 1 and 0.8 <= sleeps[0] <= 1.2
    assert "col_values" in ws.calls  # checked for an existing row before appending again


def test_lost_response_is_not_duplicated_on_retry(sheet):
    use, sleeps = sheet
    ws = use(FakeWorksheet(append_failures=[APPENDED_THEN_LOST]))
    storage.save_response(row())
    assert ws.ids() == ["P001"]
    assert ws.calls.count("append_row") == 1 and len(sleeps) == 1


def test_5xx_retried_with_exponential_backoff_then_raises(sheet):
    use, sleeps = sheet
    ws = use(FakeWorksheet(append_failures=[api_error(503)] * storage.MAX_ATTEMPTS))
    with pytest.raises(gspread.exceptions.APIError):
        storage.save_response(row())
    assert ws.calls.count("append_row") == storage.MAX_ATTEMPTS == 5
    assert len(sleeps) == 4
    for wait, nominal in zip(sleeps, [1, 2, 4, 8]):
        assert 0.8 * nominal <= wait <= 1.2 * nominal
    assert ws.ids() == []
    assert not storage.LOCAL_CSV.exists()


def test_non_retryable_error_fails_immediately(sheet):
    use, sleeps = sheet
    ws = use(FakeWorksheet(append_failures=[api_error(403)]))
    with pytest.raises(gspread.exceptions.APIError):
        storage.save_response(row())
    assert ws.calls.count("append_row") == 1 and sleeps == []


def test_retry_button_after_failed_save_does_not_duplicate(sheet):
    use, _ = sheet
    # All 5 attempts fail, but the last append actually reached the sheet.
    ws = use(FakeWorksheet(append_failures=[api_error(503)] * 4 + [APPENDED_THEN_LOST]))
    with pytest.raises(requests.exceptions.ConnectionError):
        storage.save_response(row())
    assert ws.ids() == ["P001"]
    # Participant clicks Continue again: the row is found, nothing is appended.
    ws.calls.clear()
    storage.save_response(row())
    assert ws.ids() == ["P001"]
    assert "append_row" not in ws.calls


def test_nothing_written_to_csv_when_fallback_disabled(sheet, monkeypatch):
    use, _ = sheet
    use(FakeWorksheet(append_failures=[api_error(500)] * storage.MAX_ATTEMPTS))
    with pytest.raises(gspread.exceptions.APIError):
        storage.save_response(row())
    assert not storage.LOCAL_CSV.exists()

    monkeypatch.setattr(storage, "sheets_configured", lambda: False)
    with pytest.raises(RuntimeError, match="fallback is disabled"):
        storage.save_response(row())
    assert not storage.LOCAL_CSV.exists()


def test_retryable_classification():
    assert storage._is_retryable(api_error(429))
    assert storage._is_retryable(api_error(500)) and storage._is_retryable(api_error(503))
    assert storage._is_retryable(requests.exceptions.ConnectionError())
    assert storage._is_retryable(requests.exceptions.Timeout())
    assert not storage._is_retryable(api_error(403))
    assert not storage._is_retryable(api_error(404))
    assert not storage._is_retryable(ValueError("bug"))


def test_app_shows_error_and_retry_button_then_saves_once(env, sheet):
    _, new_pid = env
    use, _ = sheet
    ws = use(FakeWorksheet(append_failures=[api_error(503)] * storage.MAX_ATTEMPTS))

    pid = new_pid("S1")
    at = start(pid)
    do_consent(at)
    do_instructions(at)
    do_comprehension(at)
    play_game(at)
    do_ec(at)
    do_demographics(at)
    at.text_area(key="q_strategy").input("Ordered around 150.")
    at.radio(key="q_instructions_clarity").set_value(4)
    click(at)

    assert page(at) == "debrief" and not at.session_state["submitted"]
    assert any("could not be saved" in e.value and "click **Continue** again" in e.value for e in at.error)
    assert [b.label for b in at.button] == ["Continue →"]  # the retry button
    assert ws.ids() == [] and not storage.LOCAL_CSV.exists()

    click(at)  # Sheets works again: participant retries
    assert page(at) == "thankyou"
    assert ws.ids() == [pid]
    assert not storage.LOCAL_CSV.exists()
