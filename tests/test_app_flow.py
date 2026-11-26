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
from scales import chen2022 as scale
from tests.conftest import ROOT

APP = str(ROOT / "app.py")
ORDERS = {"H": {"C": 200, "U": 250}, "L": {"C": 80, "U": 120}}


@pytest.fixture
def env(tmp_path, monkeypatch):
    csv_path = tmp_path / "responses.csv"
    assignment = tmp_path / "assignment.csv"
    assignment.write_text("participant_id,group,supply_order\n")
    monkeypatch.setattr(storage, "LOCAL_CSV", csv_path)
    monkeypatch.setattr(storage, "sheets_configured", lambda: False)
    monkeypatch.setattr(cfg, "ALLOW_LOCAL_CSV_FALLBACK", True)
    monkeypatch.setattr(cfg, "ASSIGNMENT_FILE", str(assignment))

    def new_pid(group: str, supply_order: str = "certain_first") -> str:
        pid = f"T{uuid.uuid4().hex[:8]}"  # unique: the server-side store outlives a test
        with assignment.open("a") as f:
            f.write(f"{pid},{group},{supply_order}\n")
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


def all_text(at) -> str:
    return "\n".join(m.value for m in at.markdown)


def do_consent(at):
    assert page(at) == "consent"
    at.radio(key="q_consent").set_value(cfg.CONSENT_YES)
    click(at)


def do_instructions(at):
    assert page(at) == "instructions"
    click(at)


def do_comprehension(at, wrong_first=False):
    assert page(at) == "comprehension"
    q2 = {"H": 660, "L": 60}[at.session_state["group"]]
    if wrong_first:
        at.number_input(key="q_comp_q1").set_value(100)  # wrong
        at.number_input(key="q_comp_q2").set_value(q2)  # right
        click(at)
        assert page(at) == "comprehension"
        comp = at.session_state["comprehension"]
        assert comp["comp_q1"] == {"attempts": 1, "passed": False, "wrong": True}
        assert comp["comp_q2"]["passed"] and comp["comp_q2"]["attempts"] == 1
        assert any(cfg.COMPREHENSION[0]["explanation"] in w.value for w in at.warning)
        assert [n.key for n in at.number_input] == ["q_comp_q1"]  # only the wrong one is asked again
    else:
        at.number_input(key="q_comp_q2").set_value(q2)
    at.number_input(key="q_comp_q1").set_value(120)
    click(at)
    assert page(at) == "game"


def play_block_round(at, block, rnd, order):
    at.number_input(key=f"q_{block}_r{rnd}_order").set_value(order)
    click(at)
    assert at.session_state["game"]["phase"] == "result"


def play_game(at, orders=None):
    group = at.session_state["group"]
    orders = orders or ORDERS[group]
    blocks = game.block_order(at.session_state["supply_order"])
    for idx, block in enumerate(blocks):
        assert at.session_state["game"]["phase"] == "intro"
        assert any(f"Block {idx + 1} of 2" in m.value for m in at.markdown)
        warnings = [w.value for w in at.warning]
        if idx == 0:
            assert not warnings
        else:  # the supply change is highlighted, the unit cost is not said to change
            (warning,) = warnings
            assert "The supply changes in this block" in warning
            assert f"stays {game.unit_cost(group)}" in warning
        click(at, f"start_block_{idx}")
        for rnd in range(1, cfg.ROUNDS_PER_BLOCK + 1):
            assert at.session_state["game"]["phase"] == "order"
            play_block_round(at, block, rnd, orders[block])
            click(at, f"next_{block}_{rnd}")
    assert at.session_state["game"]["phase"] == "end"
    assert "score" not in all_text(at).lower()  # the score is only shown after the survey
    click(at)


SEVEN_POINT = ["1 – Strongly disagree", "2", "3", "4", "5", "6", "7 – Strongly agree"]


def survey_answer(code: str) -> int:
    return 1 + sum(map(ord, code)) % 7  # deterministic 1-7 per item


def do_survey(at):
    for n, constructs in enumerate(cfg.SURVEY_PAGES, start=1):
        assert page(at) == f"survey_p{n}"
        expected = [item for c in constructs for item in scale.ITEMS if item["construct"] == c]
        labels = [item["text"] for item in expected]
        if n == cfg.ATTENTION_CHECK_PAGE:
            labels.insert(scale.ATTENTION_AFTER_ITEM, scale.ATTENTION_ITEM["text"])
        radios = list(at.radio)
        assert [r.label for r in radios] == labels
        for r in radios:
            assert r.value is None and r.horizontal and r.options == SEVEN_POINT
        text = all_text(at)
        assert scale.INSTRUCTION in text
        for c in scale.CONSTRUCTS:  # no codes or construct names shown
            assert c["name"] not in text and f"{c['code']}1" not in text
        for item in expected:
            at.radio(key=f"q_{item['code']}").set_value(survey_answer(item["code"]))
        if n == cfg.ATTENTION_CHECK_PAGE:
            at.radio(key="q_ATTN").set_value(1)
        click(at)


def do_controls(at):
    assert page(at) == "controls"
    assert [r.key for r in at.radio] == ["q_gender", "q_field_of_study", "q_risk_willingness"]
    risk = at.radio(key="q_risk_willingness")
    assert risk.horizontal and risk.value is None
    assert risk.options == ["0 – not at all willing to take risks", *map(str, range(1, 10)),
                            "10 – very willing to take risks"]
    country = at.selectbox(key="q_country_upbringing")
    assert country.value is None and country.options == cfg.COUNTRIES

    click(at)  # nothing answered: all four marked as missing
    assert page(at) == "controls"
    assert sum("Please answer this question" in m.value for m in at.markdown) == 4

    at.radio(key="q_gender").set_value("Non-binary")
    at.selectbox(key="q_country_upbringing").set_value("Austria")
    at.radio(key="q_field_of_study").set_value("Management")
    at.radio(key="q_risk_willingness").set_value(0)  # 0 is a valid answer, not "missing"
    click(at)


def do_debrief(at, feedback=""):
    assert page(at) == "debrief"
    at.text_area(key="q_strategy").input("Ordered a bit above average demand.")
    at.radio(key="q_instructions_clarity").set_value(5)
    if feedback:
        at.text_area(key="q_feedback").input(feedback)
    click(at)


def test_defaults():
    assert cfg.EC_POSITION == "after_game"
    assert cfg.SUPPLY_ORDER == "certain_first"
    assert cfg.ROUNDS_PER_BLOCK == 10


@pytest.mark.parametrize("group, cost, example, q2", [("H", 3, "960", 660), ("L", 9, "240", 60)])
def test_full_flow_saves_one_complete_row(env, group, cost, example, q2):
    csv_path, new_pid = env
    pid = new_pid(group)
    at = start(pid)
    assert (at.session_state["group"], at.session_state["supply_order"]) == (group, "certain_first")

    do_consent(at)
    text = all_text(at)
    assert f"unit cost is {cost} coins" in text and f"**{example} coins**" in text
    assert "the three best players will be announced by participant ID" in text
    assert "changes between blocks" not in text
    do_instructions(at)
    assert f"the unit cost is {cost}," in at.number_input(key="q_comp_q2").label
    do_comprehension(at, wrong_first=True)
    play_game(at)
    do_survey(at)
    do_controls(at)
    do_debrief(at)  # feedback is optional
    assert page(at) == "thankyou"

    (row,) = read_rows(csv_path)
    assert row["participant_id"] == pid
    assert (row["group"], row["unit_cost"], row["supply_order"]) == (group, str(cost), "certain_first")
    assert (row["C_position"], row["U_position"]) == ("1", "2")
    assert (row["comp_q1_attempts"], row["comp_q2_attempts"]) == ("2", "1")

    draws = game.load_sequences()
    total = 0
    for block in cfg.BLOCKS:
        for rnd in range(1, cfg.ROUNDS_PER_BLOCK + 1):
            d = draws[block][rnd - 1]
            exp = game.round_outcome(
                ORDERS[group][block], d["demand"], d["yield"] if game.is_uncertain(block) else None, cost
            )
            p = f"{block}_r{rnd}"
            assert int(row[f"{p}_order"]) == ORDERS[group][block]
            assert int(row[f"{p}_usable"]) == exp["usable"]
            assert int(row[f"{p}_demand"]) == d["demand"]
            assert float(row[f"{p}_yield"]) == d["yield"]
            assert int(row[f"{p}_sales"]) == exp["sales"]
            assert int(row[f"{p}_profit"]) == exp["profit"]
            assert float(row[f"{p}_seconds"]) >= 0
            total += exp["profit"]
    assert int(row["total_profit"]) == total

    n = cfg.ROUNDS_PER_BLOCK
    expected_score = game.score([("C", ORDERS[group]["C"])] * n + [("U", ORDERS[group]["U"])] * n, group)
    assert float(row["score"]) == expected_score
    assert f"Your score: {expected_score:.1f} / 100" in all_text(at)
    assert cfg.SCORE_EXPLANATION in all_text(at)
    assert "rank" not in all_text(at).lower()

    for p in ["consent", "instructions", "comprehension", "game", "survey_p1", "survey_p2", "survey_p3",
              "controls", "debrief"]:
        assert row[f"{p}_start"] and row[f"{p}_end"] and row[f"{p}_seconds"] != ""
    assert {c: int(row[c]) for c in scale.ITEM_CODES} == {c: survey_answer(c) for c in scale.ITEM_CODES}
    assert (row["ATTN"], row["ATTN_passed"]) == ("1", "True")
    assert (row["gender"], row["country_upbringing"], row["field_of_study"], row["risk_willingness"]) == (
        "Non-binary", "Austria", "Management", "0"
    )
    assert row["instructions_clarity"] == "5" and row["feedback"] == ""
    for old in ["sequence", "margin_order", "CH_r1_order", "UL_position", "ATTN_EC", "bachelor_field", "country",
                "environmental_concern_start", "demographics_start"]:
        assert old not in row

    # Reload after submitting -> thank-you page with the score, no second row.
    reloaded = start(pid)
    assert page(reloaded) == "thankyou" and f"{expected_score:.1f} / 100" in all_text(reloaded)
    assert len(read_rows(csv_path)) == 1


def test_blank_order_rejected_and_reload_shows_result_not_new_form(env):
    csv_path, new_pid = env
    pid = new_pid("H")
    at = start(pid)
    do_consent(at)
    do_instructions(at)
    do_comprehension(at)
    click(at, "start_block_0")

    click(at)  # confirm with no order entered
    assert at.session_state["game"]["phase"] == "order"
    assert at.error and "Please answer" in at.error[0].value

    play_block_round(at, "C", 1, 180)
    first = at.session_state["game"]["results"]["C_r1"]

    reloaded = start(pid)
    g = reloaded.session_state["game"]
    assert page(reloaded) == "game" and g["phase"] == "result" and g["round"] == 1
    assert [n.key for n in reloaded.number_input] == []  # no fresh order form
    assert g["results"]["C_r1"] == first
    assert any(m.label == "Ordered" and m.value == "180" for m in reloaded.metric)

    click(reloaded, "next_C_1")
    assert reloaded.session_state["game"]["phase"] == "order" and reloaded.session_state["game"]["round"] == 2
    assert list(reloaded.session_state["game"]["results"]) == ["C_r1"]


def test_counterbalanced_uncertain_first(env, monkeypatch):
    monkeypatch.setattr(cfg, "SUPPLY_ORDER", "counterbalanced")
    csv_path, new_pid = env
    at = start(new_pid("L", "uncertain_first"))
    assert at.session_state["supply_order"] == "uncertain_first"
    do_consent(at)
    do_instructions(at)
    do_comprehension(at)
    play_game(at)  # U first, then C (with the supply-change warning)
    do_survey(at)
    do_controls(at)
    do_debrief(at)
    (row,) = read_rows(csv_path)
    assert (row["supply_order"], row["U_position"], row["C_position"]) == ("uncertain_first", "1", "2")


def test_certain_first_ignores_supply_order_in_file(env):
    _, new_pid = env
    at = start(new_pid("H", "uncertain_first"))
    assert at.session_state["supply_order"] == "certain_first"


def test_survey_before_game_option(env, monkeypatch):
    monkeypatch.setattr(cfg, "EC_POSITION", "before_game")
    _, new_pid = env
    at = start(new_pid("L"))
    do_consent(at)
    do_survey(at)
    assert page(at) == "instructions"


# --------------------------------------------------------------------------- #
# Admin page
# --------------------------------------------------------------------------- #
def admin(password: str | None = "s3cret") -> AppTest:
    at = AppTest.from_file(APP, default_timeout=60)
    at.query_params["admin"] = "1"
    if password is None:
        at.secrets["unrelated"] = "x"  # secrets present, but no ADMIN_PASSWORD (never the real secrets.toml)
    else:
        at.secrets["ADMIN_PASSWORD"] = password
    at.run()
    assert not at.exception, at.exception
    return at


def write_rows(rows):
    for r in rows:
        storage._save_to_csv(r)


ADMIN_ROWS = [
    {"participant_id": "P001", "group": "H", "score": 90.0, "total_profit": 100, "submitted_at": "2026-11-26T10:00:00+00:00"},
    {"participant_id": "P002", "group": "L", "score": 95.5, "total_profit": 50, "submitted_at": "2026-11-26T10:05:00+00:00"},
    {"participant_id": "TEST_LIVE", "group": "H", "score": 99.9, "total_profit": 999, "submitted_at": "2026-11-26T09:00:00+00:00"},
    {"participant_id": "P003", "group": "H", "score": 90.0, "total_profit": 200, "submitted_at": "2026-11-26T10:10:00+00:00"},
    {"participant_id": "P004", "group": "L", "score": 90.0, "total_profit": 200, "submitted_at": "2026-11-26T10:20:00+00:00"},
    {"participant_id": "P005", "group": "L", "score": "", "total_profit": 10, "submitted_at": ""},  # incomplete
]


def test_admin_requires_password(env):
    write_rows(ADMIN_ROWS)
    at = admin()
    assert "pid" not in at.session_state  # an admin visit never creates a participant
    assert "pid" not in at.query_params
    assert [b.key for b in at.button if b.key == "admin_refresh"] == []
    assert not any("P002" in m.value for m in at.markdown)

    at.text_input(key="admin_password").input("wrong")
    click(at)
    assert any("Wrong password" in e.value for e in at.error)
    assert "admin_ok" not in at.session_state
    assert [b.key for b in at.button if b.key == "admin_refresh"] == []

    at.text_input(key="admin_password").input("s3cret")
    click(at)
    assert at.button(key="admin_refresh")


def test_admin_without_configured_password_is_locked(env):
    at = admin(password=None)
    assert any("ADMIN_PASSWORD is not set" in e.value for e in at.error)
    assert not at.text_input and not at.button


def test_admin_top3_excludes_test_and_incomplete_rows(env):
    write_rows(ADMIN_ROWS)
    at = admin()
    at.text_input(key="admin_password").input("s3cret")
    click(at)
    assert not any("🥇" in m.value for m in at.markdown)  # nothing read before Refresh
    click(at, "admin_refresh")

    assert at.metric[0].label == "Completed participants" and at.metric[0].value == "4"
    top = [m.value for m in at.markdown if m.value.startswith("# ")]
    # Tie at 90.0: higher total_profit first (P003, P004 > P001), then earlier submission (P003 before P004).
    assert top == ["# 🥇 P002 · 95.5", "# 🥈 P003 · 90.0", "# 🥉 P004 · 90.0"]
    full = at.dataframe[0].value
    assert list(full["participant_id"]) == ["P002", "P003", "P004", "P001"]
    assert "TEST_LIVE" not in all_text(at) and "P005" not in list(full["participant_id"])
