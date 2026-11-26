"""
Widget selling game (newsvendor experiment) with survey.

Design: profit margin between subjects (group H: unit cost 3, group L: unit cost 9),
supply within subjects (block C: certain, block U: uncertain).

Flow: consent -> [survey p1-p3] -> instructions -> comprehension check
      -> game (2 blocks) -> [survey p1-p3] -> control variables -> debrief -> thank you (with score)
      (survey position: survey_config.EC_POSITION)

Admin page (top 3 by score): ?admin=1, protected by ADMIN_PASSWORD in st.secrets.

Run with:  streamlit run app.py

How state survives a page reload
--------------------------------
st.session_state is tied to the browser's websocket connection, so a hard
reload (F5) starts a fresh session. To keep each participant where they were:

* The participant ID is written to the URL (?pid=...). On reload it is read
  back from there.
* The group (and supply order) comes from assignment.csv (if the ID is listed
  there) or from a hash of the ID, so it never changes for an ID.
* Progress (current page, answers, timestamps, game state) is mirrored into a
  server-side store keyed by participant ID and restored on reload. A confirmed
  order is stored immediately, so a reload shows that round's result and never
  a fresh order form for a round that was already played.
"""

import copy
import hmac
import re
import threading
import time
import uuid
from datetime import datetime, timezone

import pandas as pd
import streamlit as st

import game
import survey_config as cfg
from scales import chen2022 as scale
from storage import load_responses, save_response

assert [c for page in cfg.SURVEY_PAGES for c in page] == scale.CONSTRUCT_CODES, (
    "SURVEY_PAGES must list every construct of scales/chen2022.py once, in the published order."
)
SURVEY_PAGE_IDS = [f"survey_p{i}" for i in range(1, len(cfg.SURVEY_PAGES) + 1)]

EC_POSITIONS = {"before_game": "instructions", "after_game": "controls"}  # setting -> page the survey precedes
assert cfg.EC_POSITION in EC_POSITIONS, f"EC_POSITION must be one of {list(EC_POSITIONS)}"

PAGES = ["consent", "instructions", "comprehension", "game", "controls", "debrief", "thankyou"]
_at = PAGES.index(EC_POSITIONS[cfg.EC_POSITION])
PAGES[_at:_at] = SURVEY_PAGE_IDS
LAST_QUESTION_PAGE = PAGES[-2]  # submitting this page saves the row
QUESTION_PAGES = {
    "consent": (cfg.CONSENT_TEXT, cfg.CONSENT_QUESTIONS),
    **{
        page_id: (
            scale.INSTRUCTION,
            scale.questions(constructs, attention_check=scale.ATTENTION_CHECK and n == cfg.ATTENTION_CHECK_PAGE),
        )
        for n, (page_id, constructs) in enumerate(zip(SURVEY_PAGE_IDS, cfg.SURVEY_PAGES), start=1)
    },
    "controls": (cfg.CONTROLS_INTRO, cfg.CONTROLS),
    "debrief": (cfg.DEBRIEF_INTRO, cfg.DEBRIEF),
}
ALL_QUESTIONS = [q for _, qs in QUESTION_PAGES.values() for q in qs]
PERSISTED_KEYS = [
    "pid", "group", "supply_order", "page", "answers", "timestamps", "submitted", "comprehension", "game",
]
PID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

_ids = [q["id"] for q in ALL_QUESTIONS] + [q["id"] for q in cfg.COMPREHENSION]
assert len(_ids) == len(set(_ids)), "Question ids in survey_config.py must be unique."


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def seconds_between(start: str | None, end: str | None) -> float | str:
    if not start or not end:
        return ""
    return (datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds()


def money(x: float) -> str:
    return f"{x:,.0f} {cfg.CURRENCY}"


@st.cache_data
def draws() -> dict[str, list[dict]]:
    return game.load_sequences()


@st.cache_resource
def _progress_store() -> tuple[dict, threading.Lock]:
    """Server-side store shared by all sessions: {pid: snapshot of progress}."""
    return {}, threading.Lock()


def persist() -> None:
    store, lock = _progress_store()
    snapshot = copy.deepcopy({k: st.session_state[k] for k in PERSISTED_KEYS})
    with lock:
        store[st.session_state.pid] = snapshot


def init_participant() -> None:
    if "pid" in st.session_state:
        return
    pid = st.query_params.get("pid", "")
    if not PID_PATTERN.match(pid):
        pid = uuid.uuid4().hex[:12]
    st.query_params["pid"] = pid

    store, lock = _progress_store()
    with lock:
        saved = copy.deepcopy(store.get(pid))
    if saved:
        st.session_state.update(saved)
    else:
        st.session_state.update(
            pid=pid,
            **game.assign(pid),  # group, supply_order
            page=PAGES[0],
            answers={},
            timestamps={},
            submitted=False,
            comprehension={q["id"]: {"attempts": 0, "passed": False, "wrong": False} for q in cfg.COMPREHENSION},
            game={"block_idx": 0, "round": 1, "phase": "intro", "order_shown_at": None, "results": {}},
        )
        persist()


def mark_page_start(page: str) -> None:
    key = f"{page}_start"
    if key not in st.session_state.timestamps:
        st.session_state.timestamps[key] = now_iso()
        persist()


def go_to(next_page: str) -> None:
    st.session_state.timestamps[f"{st.session_state.page}_end"] = now_iso()
    st.session_state.page = next_page
    persist()
    st.rerun()


def next_page_of(page: str) -> str:
    return PAGES[PAGES.index(page) + 1]


# --------------------------------------------------------------------------- #
# Questions
# --------------------------------------------------------------------------- #
def widget_key(q: dict) -> str:
    return f"q_{q['id']}"


def is_missing(q: dict, value) -> bool:
    if not q.get("required", True):
        return False
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, list):
        return len(value) == 0
    return False


def render_widget(q: dict) -> None:
    key, label, kind = widget_key(q), q["label"], q["type"]
    common = {"key": key, "help": q.get("help")}
    if kind == "radio":
        st.radio(label, q["options"], index=None, horizontal=q.get("horizontal", False), **common)
    elif kind == "select":
        st.selectbox(label, q["options"], index=None, placeholder=q.get("placeholder", "Please choose…"), **common)
    elif kind == "likert":
        # Either inline options/labels (e.g. from scales/) or a named scale from survey_config.SCALES.
        labels = q.get("labels") or cfg.SCALES[q["scale"]]
        options = q.get("options") or list(labels)
        st.radio(label, options=options, index=None, horizontal=True, format_func=labels.get, **common)
    elif kind == "multi":
        st.multiselect(label, q["options"], placeholder="Select all that apply", **common)
    elif kind == "text":
        st.text_input(label, **common)
    elif kind == "textarea":
        st.text_area(label, **common)
    elif kind == "number":
        st.number_input(
            label, min_value=q.get("min"), max_value=q.get("max"), step=q.get("step", 1),
            value=None, placeholder=q.get("placeholder", "Enter a number"), **common,
        )
    else:
        raise ValueError(f"Unknown question type {kind!r} for question {q['id']!r}")


def question_form(
    page: str, questions: list[dict], submit_label: str = "Continue →", notes: dict | None = None
) -> dict | None:
    """Render questions in a form. Returns the answers once all required ones are filled.

    notes: optional {question id: text} shown above a question (e.g. feedback after a wrong answer).
    """
    missing_key = f"_missing_{page}"
    missing = st.session_state.get(missing_key, set())
    notes = notes or {}

    with st.form(f"form_{page}"):
        for q in questions:
            if q["id"] in missing:
                st.markdown(":red[**Please answer this question.**]")
            if q["id"] in notes:
                st.warning(notes[q["id"]])
            render_widget(q)
            st.write("")
        submitted = st.form_submit_button(submit_label, type="primary")

    if missing:
        st.error(f"Please answer all questions ({len(missing)} still missing, marked in red).")

    if not submitted:
        return None
    values = {q["id"]: st.session_state.get(widget_key(q)) for q in questions}
    now_missing = {q["id"] for q in questions if is_missing(q, values[q["id"]])}
    if now_missing:
        st.session_state[missing_key] = now_missing
        st.rerun()
    st.session_state.pop(missing_key, None)
    return values


# --------------------------------------------------------------------------- #
# Saving
# --------------------------------------------------------------------------- #
def format_answer(value):
    if isinstance(value, list):
        return "; ".join(map(str, value))
    return "" if value is None else value


def total_profit() -> int:
    return sum(r["profit"] for r in st.session_state.game["results"].values())


def block_order() -> list[str]:
    return game.block_order(st.session_state.supply_order)


def unit_cost() -> int:
    return game.unit_cost(st.session_state.group)


def current_score() -> float | None:
    """Score over all rounds played so far (shared formula: game.score)."""
    results = st.session_state.game["results"]
    orders = [
        (block, results[game.round_key(block, rnd)]["order"])
        for block in cfg.BLOCKS
        for rnd in range(1, cfg.ROUNDS_PER_BLOCK + 1)
        if game.round_key(block, rnd) in results
    ]
    return game.score(orders, st.session_state.group)


def build_row() -> dict:
    ts = st.session_state.timestamps
    group = st.session_state.group
    row = {
        "participant_id": st.session_state.pid,
        "group": group,
        "unit_cost": game.unit_cost(group),
        "supply_order": st.session_state.supply_order,
        "started_at": ts.get("consent_start", ""),
        "submitted_at": ts.get(f"{LAST_QUESTION_PAGE}_end", ""),
        "total_seconds": seconds_between(ts.get("consent_start"), ts.get(f"{LAST_QUESTION_PAGE}_end")),
    }
    for q in cfg.COMPREHENSION:
        row[f"{q['id']}_attempts"] = st.session_state.comprehension[q["id"]]["attempts"]
    for page in PAGES[:-1]:
        row[f"{page}_start"] = ts.get(f"{page}_start", "")
        row[f"{page}_end"] = ts.get(f"{page}_end", "")
        row[f"{page}_seconds"] = seconds_between(ts.get(f"{page}_start"), ts.get(f"{page}_end"))
    row["total_profit"] = total_profit()
    score = current_score()
    row["score"] = "" if score is None else score

    results = st.session_state.game["results"]
    order = block_order()
    for block in cfg.BLOCKS:  # columns named by block, not position
        row[f"{block}_position"] = order.index(block) + 1
        for rnd in range(1, cfg.ROUNDS_PER_BLOCK + 1):
            result = results.get(game.round_key(block, rnd), {})
            for field in game.ROUND_FIELDS:
                row[f"{game.round_key(block, rnd)}_{field}"] = result.get(field, "")

    for q in ALL_QUESTIONS:
        row[q["id"]] = format_answer(st.session_state.answers.get(q["id"]))
    attn = scale.ATTENTION_ITEM["code"]
    if attn in row:  # the attention check is not part of any construct
        row[f"{attn}_passed"] = scale.attention_passed(row[attn])
    return row


# --------------------------------------------------------------------------- #
# Question pages
# --------------------------------------------------------------------------- #
def page_questions(page: str) -> None:
    intro, questions = QUESTION_PAGES[page]
    st.markdown(intro)
    values = question_form(page, questions)
    if values is None:
        return
    st.session_state.answers.update(values)

    if page == "consent" and values["consent"] != cfg.CONSENT_YES:
        go_to("declined")
    elif page == LAST_QUESTION_PAGE:
        submit()
    else:
        go_to(next_page_of(page))


def submit() -> None:
    end_key = f"{LAST_QUESTION_PAGE}_end"
    st.session_state.timestamps[end_key] = now_iso()
    try:
        with st.spinner("Saving your responses…"):
            save_response(build_row())
    except Exception as exc:
        # Keep the participant on this page so they can retry; answers are kept.
        st.session_state.timestamps.pop(end_key, None)
        st.error(
            "Sorry, your responses could not be saved. Please click **Continue** again. "
            f"If this keeps happening, contact {cfg.CONTACT_EMAIL}."
        )
        print(f"[save error] pid={st.session_state.pid}: {exc!r}")
        return
    st.session_state.submitted = True
    st.session_state.page = "thankyou"
    persist()
    st.rerun()


# --------------------------------------------------------------------------- #
# Instructions and comprehension check
# --------------------------------------------------------------------------- #
def instructions_text() -> str:
    return cfg.instructions_text(st.session_state.group)


def instructions_expander() -> None:
    with st.expander("📖 Game instructions"):
        st.markdown(instructions_text())


def page_instructions() -> None:
    st.markdown("### How the game works")
    st.markdown(instructions_text())
    if st.button("I have read the instructions →", type="primary"):
        go_to(next_page_of("instructions"))


def page_comprehension() -> None:
    instructions_expander()
    st.markdown(cfg.COMPREHENSION_INTRO)
    comp = st.session_state.comprehension
    comp_questions = cfg.comprehension(st.session_state.group)  # Q2 uses the participant's unit cost

    for q in comp_questions:
        if comp[q["id"]]["passed"]:
            st.success(f"✓ {q['label']} **{q['answer']:,}**")

    pending = [q for q in comp_questions if not comp[q["id"]]["passed"]]
    questions = [
        {"id": q["id"], "type": "number", "label": q["label"], "min": None, "max": None, "step": 1}
        for q in pending
    ]
    notes = {
        q["id"]: f"Not quite – please try again. {q['explanation']}" for q in pending if comp[q["id"]]["wrong"]
    }
    values = question_form("comprehension", questions, submit_label="Check answers", notes=notes)
    if values is None:
        return

    for q in pending:
        state = comp[q["id"]]
        state["attempts"] += 1
        state["passed"] = values[q["id"]] == q["answer"]
        state["wrong"] = not state["passed"]
    persist()
    if all(s["passed"] for s in comp.values()):
        go_to(next_page_of("comprehension"))
    st.rerun()


# --------------------------------------------------------------------------- #
# Game
# --------------------------------------------------------------------------- #
SUPPLY_LABEL = {"certain": "Certain supply", "uncertain": "Uncertain supply"}
SUPPLY_COLOR = {"certain": "blue", "uncertain": "orange"}


def block_badges(block: str) -> str:
    supply = cfg.BLOCKS[block]["supply"]
    return (
        f":gray-background[**Unit cost {unit_cost()} {cfg.CURRENCY}**] "
        f":{SUPPLY_COLOR[supply]}-background[**{SUPPLY_LABEL[supply]}**]"
    )


def game_progress() -> float:
    """Share of the game done, for the progress bar."""
    return len(st.session_state.game["results"]) / cfg.N_ROUNDS


def round_history_table(block: str, upto: int) -> None:
    rows = []
    for rnd in range(1, upto):
        r = st.session_state.game["results"][game.round_key(block, rnd)]
        rows.append(
            {"Round": rnd, "Ordered": r["order"], "Usable": r["usable"], "Demand": r["demand"],
             "Sold": r["sales"], "Profit": r["profit"]}
        )
    if rows:
        st.markdown("**Earlier rounds in this block**")
        st.dataframe(pd.DataFrame(rows), hide_index=True)


def block_intro(order: list[str], idx: int) -> None:
    block = order[idx]
    supply = cfg.BLOCKS[block]["supply"]
    st.markdown(f"## Block {idx + 1} of {len(order)}")
    st.markdown(block_badges(block))

    if idx > 0:
        prev_supply = cfg.BLOCKS[order[idx - 1]]["supply"]
        if prev_supply != supply:
            st.warning(
                f"⚠️ **The supply changes in this block: from {prev_supply} to {supply}.**\n\n"
                f"Before: {cfg.SUPPLY_RULE[prev_supply]}\n\n"
                f"**Now: {cfg.SUPPLY_RULE[supply]}**\n\n"
                f"Your unit cost stays {unit_cost()} {cfg.CURRENCY}."
            )

    st.markdown(
        f"""
In this block ({cfg.ROUNDS_PER_BLOCK} rounds):

- **Unit cost:** {unit_cost()} {cfg.CURRENCY} per usable widget
- **Selling price:** {cfg.PRICE} {cfg.CURRENCY} per widget sold
- **Supply:** {cfg.SUPPLY_RULE[supply]}
- **Demand:** {cfg.DEMAND_RULE}
"""
    )
    instructions_expander()
    if st.button(f"Start block {idx + 1} →", type="primary", key=f"start_block_{idx}"):
        g = st.session_state.game
        g.update(phase="order", round=1, order_shown_at=None)
        persist()
        st.rerun()


def round_header(order: list[str], idx: int, rnd: int) -> None:
    block = order[idx]
    st.markdown(f"#### Block {idx + 1} of {len(order)} · Round {rnd} of {cfg.ROUNDS_PER_BLOCK}")
    st.markdown(block_badges(block))
    c1, c2, c3 = st.columns(3)
    c1.metric("Unit cost", money(unit_cost()))
    c2.metric("Selling price", money(cfg.PRICE))
    c3.metric("Total profit so far", money(total_profit()))
    st.caption(f"**Supply:** {cfg.SUPPLY_RULE[cfg.BLOCKS[block]['supply']]}  \n**Demand:** {cfg.DEMAND_RULE}")
    instructions_expander()


def play_order(order: list[str], idx: int, rnd: int) -> None:
    g = st.session_state.game
    block = order[idx]
    key = game.round_key(block, rnd)
    if g["order_shown_at"] is None:
        g["order_shown_at"] = time.time()
        persist()

    round_header(order, idx, rnd)
    round_history_table(block, rnd)
    question = {
        "id": f"{key}_order", "type": "number", "min": cfg.ORDER_MIN, "max": cfg.ORDER_MAX, "step": 1,
        "label": f"How many widgets do you order? ({cfg.ORDER_MIN}–{cfg.ORDER_MAX})",
        "placeholder": "Enter your order",
    }
    values = question_form(f"order_{key}", [question], submit_label="Confirm order")
    if values is None or key in g["results"]:  # a confirmed order is final
        return

    draw = draws()[block][rnd - 1]
    yield_ = draw["yield"] if game.is_uncertain(block) else None
    outcome = game.round_outcome(values[question["id"]], draw["demand"], yield_, unit_cost())
    outcome["yield"] = draw["yield"]
    outcome["seconds"] = round(time.time() - g["order_shown_at"], 1)
    g["results"][key] = outcome
    g["phase"] = "result"
    persist()  # store immediately: a reload now shows the result, never a new order form
    st.rerun()


def play_result(order: list[str], idx: int, rnd: int) -> None:
    g = st.session_state.game
    block = order[idx]
    r = g["results"][game.round_key(block, rnd)]

    round_header(order, idx, rnd)
    st.markdown("**Result of this round**")
    c = st.columns(4)
    c[0].metric("Ordered", r["order"])
    c[1].metric("Usable", r["usable"])
    c[2].metric("Demand", r["demand"])
    c[3].metric("Sold", r["sales"])
    c = st.columns(4)
    c[0].metric("Revenue", money(r["revenue"]))
    c[1].metric("Cost", money(r["cost"]))
    c[2].metric("Profit", money(r["profit"]))
    c[3].metric("Total profit", money(total_profit()))
    if r["leftover"]:
        st.caption(f"{r['leftover']} unsold widget(s) were scrapped.")
    round_history_table(block, rnd)

    last_round = rnd == cfg.ROUNDS_PER_BLOCK
    last_block = idx == len(order) - 1
    label = "Next round →"
    if last_round:
        label = "See your total profit →" if last_block else f"Continue to block {idx + 2} →"
    if st.button(label, type="primary", key=f"next_{block}_{rnd}"):
        if not last_round:
            g.update(round=rnd + 1, phase="order", order_shown_at=None)
        elif not last_block:
            g.update(block_idx=idx + 1, round=1, phase="intro", order_shown_at=None)
        else:
            g.update(phase="end")
        persist()
        st.rerun()


def game_end() -> None:
    st.markdown("## Game over")
    st.metric("Your total profit", money(total_profit()))
    st.markdown("Thank you for playing. Next, a few short questions.")
    if st.button("Continue →", type="primary"):
        go_to(next_page_of("game"))


def page_game() -> None:
    g = st.session_state.game
    order = block_order()
    idx, rnd, phase = g["block_idx"], g["round"], g["phase"]
    if phase == "intro":
        block_intro(order, idx)
    elif phase == "order":
        play_order(order, idx, rnd)
    elif phase == "result":
        play_result(order, idx, rnd)
    elif phase == "end":
        game_end()


# --------------------------------------------------------------------------- #
# End pages
# --------------------------------------------------------------------------- #
def page_thankyou() -> None:
    st.markdown(cfg.THANKYOU_TEXT)
    score = current_score()
    if score is not None:
        st.markdown(f"### Your score: {score:.1f} / 100")
        st.markdown(cfg.SCORE_EXPLANATION)
    if cfg.COMPLETION_CODE:
        st.success(f"Your completion code: **{cfg.COMPLETION_CODE}**")
    st.caption(f"Participant ID: {st.session_state.pid}")


def page_declined() -> None:
    st.markdown(cfg.DECLINED_TEXT)


# --------------------------------------------------------------------------- #
# Admin page (?admin=1): top 3 by score, for the announcement at the end of the session
# --------------------------------------------------------------------------- #
MEDALS = ["🥇", "🥈", "🥉"]


def admin_password() -> str:
    try:
        return str(st.secrets.get("ADMIN_PASSWORD", "") or "")
    except Exception:  # no secrets.toml at all
        return ""


def page_admin() -> None:
    st.markdown("## Admin: top players")
    expected = admin_password()
    if not expected:
        st.error("ADMIN_PASSWORD is not set in the Streamlit secrets.")
        return
    if not st.session_state.get("admin_ok"):
        with st.form("admin_login"):
            password = st.text_input("Password", type="password", key="admin_password")
            submitted = st.form_submit_button("Log in", type="primary")
        if submitted:
            if hmac.compare_digest((password or "").encode(), expected.encode()):
                st.session_state.admin_ok = True
                st.rerun()
            st.error("Wrong password.")
        return

    st.caption(
        f"Reads the Sheet once per click (no auto-refresh). IDs starting with {cfg.TEST_ID_PREFIX} "
        "and incomplete rows are left out. Ties: higher total profit, then earlier submission."
    )
    if st.button("Refresh", type="primary", key="admin_refresh"):
        try:
            with st.spinner("Reading the Sheet…"):
                st.session_state.admin_ranking = game.ranking(load_responses())
            st.session_state.admin_refreshed_at = datetime.now().strftime("%H:%M:%S")
        except Exception as exc:
            st.error(f"Could not read the responses: {exc!r}")
            return

    ranking = st.session_state.get("admin_ranking")
    if ranking is None:
        st.info("Click **Refresh** to read the Sheet.")
        return
    st.caption(f"Last refreshed at {st.session_state.admin_refreshed_at}.")
    st.metric("Completed participants", len(ranking))
    for medal, entry in zip(MEDALS, ranking[:3]):
        st.markdown(f"# {medal} {entry['participant_id']} · {entry['score']:.1f}")
    with st.expander("Full ranking"):
        st.dataframe(pd.DataFrame(ranking), hide_index=True)


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
st.set_page_config(page_title=cfg.STUDY_TITLE, page_icon="📦", layout="centered")
# Hide Streamlit's menu, deploy button and footer so participants only see the study.
st.markdown(
    """<style>
    #MainMenu, header [data-testid="stToolbar"], footer {visibility: hidden;}
    </style>""",
    unsafe_allow_html=True,
)

if st.query_params.get("admin") == "1":
    page_admin()
    st.stop()

init_participant()

# Finished participants always see the thank-you page (no double submissions).
if st.session_state.submitted:
    st.session_state.page = "thankyou"

page = st.session_state.page
if page in PAGES:
    within = game_progress() if page == "game" else 0
    st.progress(min(1.0, (PAGES.index(page) + within) / (len(PAGES) - 1)))
mark_page_start(page)

if page in QUESTION_PAGES:
    page_questions(page)
elif page == "instructions":
    page_instructions()
elif page == "comprehension":
    page_comprehension()
elif page == "game":
    page_game()
elif page == "thankyou":
    page_thankyou()
elif page == "declined":
    page_declined()
