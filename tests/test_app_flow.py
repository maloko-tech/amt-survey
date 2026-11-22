"""End-to-end tests of the study flow with Streamlit's AppTest (headless).

Responses go to a temporary CSV and assignments come from a temporary
assignment.csv; Google Sheets and the real data/ folder are never touched.
"""

import csv
import uuid

import pytest
from streamlit.testing.v1 import AppTest

import game
import storage
import survey_config as cfg
from scales import environmental_concern as ec
from tests.conftest import ROOT

APP = str(ROOT / "app.py")
ORDERS = {"CH": 200, "CL": 80, "UH": 250, "UL": 120}


@pytest.fixture
def env(tmp_path, monkeypatch):
    csv_path = tmp_path / "responses.csv"
    assignment = tmp_path / "assignment.csv"
    assignment.write_text("participant_id,sequence\n")
    monkeypatch.setattr(storage, "LOCAL_CSV", csv_path)
    monkeypatch.setattr(storage, "sheets_configured", lambda: False)
    monkeypatch.setattr(cfg, "ALLOW_LOCAL_CSV_FALLBACK", True)
    monkeypatch.setattr(cfg, "ASSIGNMENT_FILE", str(assignment))

    def new_pid(sequence: str) -> str:
        pid = f"T{uuid.uuid4().hex[:8]}"  # unique: the server-side store outlives a test
        with assignment.open("a") as f:
            f.write(f"{pid},{sequence}\n")
        return pid

    return csv_path, new_pid


def start(pid: str) -> AppTest:
    at = AppTest.from_file(APP, default_timeout=60)
    at.query_params["pid"] = pid
    at.run()
    assert not at.exception, at.exception
    return at


def page(at):
    return at.session_state["page"]


def click(at, key=None):
    (at.button(key=key) if key else at.button[0]).click().run()
    assert not at.exception, at.exception


def read_rows(path):
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def do_consent(at):
    assert page(at) == "consent"
    at.radio(key="q_consent").set_value(cfg.CONSENT_YES)
    click(at)


def do_instructions(at):
    assert page(at) == "instructions"
    click(at)


def do_comprehension(at, wrong_first=False):
    assert page(at) == "comprehension"
    if wrong_first:
        at.number_input(key="q_comp_q1").set_value(100)  # wrong
        at.number_input(key="q_comp_q2").set_value(660)  # right
        click(at)
        assert page(at) == "comprehension"
        comp = at.session_state["comprehension"]
        assert comp["comp_q1"] == {"attempts": 1, "passed": False, "wrong": True}
        assert comp["comp_q2"]["passed"] and comp["comp_q2"]["attempts"] == 1
        assert any(cfg.COMPREHENSION[0]["explanation"] in w.value for w in at.warning)
        assert [n.key for n in at.number_input] == ["q_comp_q1"]  # only the wrong one is asked again
    else:
        at.number_input(key="q_comp_q2").set_value(660)
    at.number_input(key="q_comp_q1").set_value(120)
    click(at)
    assert page(at) == "game"


def play_block_round(at, block, rnd, order):
    at.number_input(key=f"q_{block}_r{rnd}_order").set_value(order)
    click(at)
    assert at.session_state["game"]["phase"] == "result"


def play_game(at, orders=ORDERS):
    sequence = at.session_state["sequence"]
    for idx, block in enumerate(cfg.SEQUENCES[sequence]):
        assert at.session_state["game"]["phase"] == "intro"
        assert any(f"Block {idx + 1} of 4" in m.value for m in at.markdown)
        click(at, f"start_block_{idx}")
        for rnd in range(1, cfg.ROUNDS_PER_BLOCK + 1):
            assert at.session_state["game"]["phase"] == "order"
            play_block_round(at, block, rnd, orders[block])
            click(at, f"next_{block}_{rnd}")
    assert at.session_state["game"]["phase"] == "end"
    click(at)


EC_ANSWERS = {"EC1": 7, "EC2": 6, "EC3": 1, "EC4": 4}  # 6 and 7 only exist on the 7-point scale


def do_ec(at):
    assert page(at) == ec.PAGE_ID
    radios = [r for r in at.radio if r.key in {f"q_{c}" for c in ec.ITEM_CODES}]
    assert [r.label for r in radios] == [item["text"] for item in ec.ITEMS]
    for r in radios:
        assert r.value is None and r.horizontal
        assert r.options == ["1 – Strongly disagree", "2", "3", "4", "5", "6", "7 – Strongly agree"]
    for code, value in EC_ANSWERS.items():
        at.radio(key=f"q_{code}").set_value(value)
    click(at)


def do_demographics(at):
    assert page(at) == "demographics"
    at.radio(key="q_gender").set_value("Female")
    at.text_input(key="q_country").input("Finland")
    at.radio(key="q_bachelor_field").set_value("Engineering")
    click(at)


def do_debrief(at, feedback=""):
    assert page(at) == "debrief"
    at.text_area(key="q_strategy").input("Ordered a bit above average demand.")
    at.radio(key="q_instructions_clarity").set_value(5)
    if feedback:
        at.text_area(key="q_feedback").input(feedback)
    click(at)


def test_ec_after_game_is_default():
    assert cfg.EC_POSITION == "after_game"


def test_full_flow_s3_saves_one_complete_row(env):
    csv_path, new_pid = env
    pid = new_pid("S3")
    at = start(pid)
    assert at.session_state["sequence"] == "S3"

    do_consent(at)
    do_instructions(at)
    do_comprehension(at, wrong_first=True)
    play_game(at)
    do_ec(at)
    do_demographics(at)
    do_debrief(at)  # feedback is optional
    assert page(at) == "thankyou"

    (row,) = read_rows(csv_path)
    assert row["participant_id"] == pid
    assert (row["sequence"], row["supply_order"], row["margin_order"]) == ("S3", "uncertain_first", "high_first")
    assert (row["comp_q1_attempts"], row["comp_q2_attempts"]) == ("2", "1")
    assert {b: row[f"{b}_position"] for b in cfg.BLOCKS} == {"UH": "1", "UL": "2", "CH": "3", "CL": "4"}

    draws = game.load_sequences()
    total = 0
    for block in cfg.BLOCKS:
        for rnd in range(1, cfg.ROUNDS_PER_BLOCK + 1):
            d = draws[block][rnd - 1]
            exp = game.round_outcome(
                ORDERS[block], d["demand"], d["yield"] if game.is_uncertain(block) else None, game.unit_cost(block)
            )
            p = f"{block}_r{rnd}"
            assert int(row[f"{p}_order"]) == ORDERS[block]
            assert int(row[f"{p}_usable"]) == exp["usable"]
            assert int(row[f"{p}_demand"]) == d["demand"]
            assert float(row[f"{p}_yield"]) == d["yield"]
            assert int(row[f"{p}_sales"]) == exp["sales"]
            assert int(row[f"{p}_profit"]) == exp["profit"]
            assert float(row[f"{p}_seconds"]) >= 0
            total += exp["profit"]
    assert int(row["total_profit"]) == total

    for p in ["consent", "instructions", "comprehension", "game", ec.PAGE_ID, "demographics", "debrief"]:
        assert row[f"{p}_start"] and row[f"{p}_end"] and row[f"{p}_seconds"] != ""
    assert {c: int(row[c]) for c in ec.ITEM_CODES} == EC_ANSWERS
    assert (row["gender"], row["country"], row["bachelor_field"]) == ("Female", "Finland", "Engineering")
    assert row["instructions_clarity"] == "5" and row["feedback"] == ""
    for old in ["condition", "pretest_start", "stimulus_start", "posttest_start", "age", "manip_check"]:
        assert old not in row

    # Reload after submitting -> thank-you page, no second row.
    assert page(start(pid)) == "thankyou"
    assert len(read_rows(csv_path)) == 1


def test_blank_order_rejected_and_reload_shows_result_not_new_form(env):
    csv_path, new_pid = env
    pid = new_pid("S1")
    at = start(pid)
    do_consent(at)
    do_instructions(at)
    do_comprehension(at)
    click(at, "start_block_0")

    click(at)  # confirm with no order entered
    assert at.session_state["game"]["phase"] == "order"
    assert at.error and "Please answer" in at.error[0].value

    play_block_round(at, "CH", 1, 180)
    first = at.session_state["game"]["results"]["CH_r1"]

    reloaded = start(pid)
    g = reloaded.session_state["game"]
    assert page(reloaded) == "game" and g["phase"] == "result" and g["round"] == 1
    assert [n.key for n in reloaded.number_input] == []  # no fresh order form
    assert g["results"]["CH_r1"] == first
    assert any(m.label == "Ordered" and m.value == "180" for m in reloaded.metric)

    click(reloaded, "next_CH_1")
    assert reloaded.session_state["game"]["phase"] == "order" and reloaded.session_state["game"]["round"] == 2
    assert list(reloaded.session_state["game"]["results"]) == ["CH_r1"]


def test_ec_before_game_option(env, monkeypatch):
    monkeypatch.setattr(cfg, "EC_POSITION", "before_game")
    _, new_pid = env
    at = start(new_pid("S2"))
    do_consent(at)
    do_ec(at)
    assert page(at) == "instructions"
