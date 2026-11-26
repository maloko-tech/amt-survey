from collections import Counter

import pandas as pd
import pytest

import analysis
import game
import make_participants
import make_sequences
import survey_config as cfg
from scales import chen2022 as scale


# --------------------------------------------------------------------------- #
# Profit function and rounding
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("group, cost, profit", [("H", 3, 960), ("L", 9, 240)])
def test_worked_example_per_group(group, cost, profit):
    # Participant's unit cost, uncertain supply: order 150, 120 usable (Z = 0.80), demand 110.
    r = game.round_outcome(order=150, demand=110, yield_=0.80, cost=cost)
    assert r == {
        "order": 150, "usable": 120, "demand": 110, "sales": 110,
        "revenue": 1320, "cost": 120 * cost, "leftover": 10, "profit": profit,
    }
    assert cfg.example_outcome(group)["profit"] == profit
    text = cfg.instructions_text(group)
    assert f"**{profit:,} coins**" in text
    assert f"unit cost is {cost} coins" in text and f"120 × {cost} = **{120 * cost:,} coins**" in text
    assert "Your goal is to earn as much profit as possible. At the end of the session,\nthe three best players will be announced by participant ID." in text
    assert "changes between blocks" not in text and "{" not in text


@pytest.mark.parametrize("group, cost, answer", [("H", 3, 660), ("L", 9, 60)])
def test_comprehension_q2_per_group(group, cost, answer):
    assert game.round_outcome(order=100, demand=80, yield_=None, cost=cost)["profit"] == answer
    q1, q2 = cfg.comprehension(group)
    assert q2["answer"] == answer
    assert f"the unit cost is {cost}," in q2["label"]
    assert f"100 × {cost} = {100 * cost}" in q2["explanation"]
    assert q1["answer"] == 120  # Q1 is the same for both groups


def test_comprehension_q1_usable_120():
    assert game.usable_units(200, 0.60) == 120


@pytest.mark.parametrize(
    "order, z, expected",
    [
        (5, 0.50, 3),  # 2.5 -> 3 (half up, not banker's rounding)
        (15, 0.70, 11),  # 10.5 -> 11 (float 0.7 * 15 = 10.4999...)
        (101, 0.45, 45),  # 45.45 -> 45
        (999, 0.41, 410),  # 409.59 -> 410
        (1000, 1.00, 1000),
        (0, 0.40, 0),
    ],
)
def test_usable_units_round_half_up(order, z, expected):
    assert game.usable_units(order, z) == expected


def test_certain_supply_all_usable():
    assert game.usable_units(237, None) == 237


def test_leftover_and_salvage_zero():
    r = game.round_outcome(order=300, demand=0, yield_=None, cost=3)
    assert r["sales"] == 0 and r["profit"] == -900


# --------------------------------------------------------------------------- #
# Expected profit and optimal orders
# --------------------------------------------------------------------------- #
EXPECTED_OPTIMA = {
    ("H", "C"): (225, 1012.5), ("H", "U"): (303, 954.0), ("L", "C"): (75, 112.5), ("L", "U"): (101, 106.0),
}


@pytest.mark.parametrize("group, block", list(EXPECTED_OPTIMA))
def test_argmax_expected_profit(group, block):
    q_star, e_star = game.optimal_order(block, group)
    exp_q, exp_e = EXPECTED_OPTIMA[(group, block)]
    assert q_star == exp_q == cfg.OPTIMAL_ORDERS[group][block]
    assert abs(e_star - exp_e) <= 2
    assert abs(e_star - cfg.OPTIMAL_EXPECTED_PROFIT[group][block]) <= 2


def test_expected_profit_certain_closed_form():
    # 12 * (225 - 225^2/600) - 3 * 225
    assert float(game.expected_profit(225, "C", "H")) == pytest.approx(1012.5)
    assert float(game.expected_profit(400, "C", "H")) == pytest.approx(12 * 150 - 3 * 400)


# --------------------------------------------------------------------------- #
# Score
# --------------------------------------------------------------------------- #
def test_score_low_margin_examples():
    n = cfg.ROUNDS_PER_BLOCK
    # E[pi(60)] = 108 vs E[pi(75)] = 112.5 with certain supply -> 96 %.
    assert game.score([("C", 60)] * n, "L") == 96.0
    # 75 is optimal (100 %), E[pi(45)] = 94.5 -> 84 %; mean 92 %.
    assert game.score([("C", 75), ("C", 45)] * (n // 2), "L") == 92.0


def test_score_over_both_blocks_uses_each_blocks_optimum():
    n = cfg.ROUNDS_PER_BLOCK
    assert game.score([("C", 225)] * n + [("U", 303)] * n, "H") == 100.0
    assert game.score([("C", 75)] * n + [("U", 101)] * n, "L") == 100.0
    # Same order 60 in all rounds: 96 % in C, about 83.5 % in U (optimum 101) -> 89.8.
    assert game.score([("C", 60)] * n + [("U", 60)] * n, "L") == 89.8
    # The H optimum is far from optimal for L, and the reverse.
    assert game.score([("C", 225)] * n, "L") < 0 < game.score([("C", 75)] * n, "H") < 100


def test_score_matches_profit_share_and_rounding():
    orders = [("C", 200), ("U", 250), ("U", 0)]
    shares = [game.profit_share(q, b, "H") for b, q in orders]
    assert game.score(orders, "H") == round(100 * sum(shares) / 3, 1)
    assert game.profit_share(0, "U", "H") == 0
    assert game.score([], "H") is None


# --------------------------------------------------------------------------- #
# Ranking (admin page)
# --------------------------------------------------------------------------- #
def test_ranking_excludes_test_and_incomplete_rows_and_breaks_ties():
    rows = [
        {"participant_id": "P1", "score": "90", "total_profit": "100", "submitted_at": "2026-11-26T10:00:00+00:00"},
        {"participant_id": "P2", "score": 95.5, "total_profit": 50, "submitted_at": "2026-11-26T10:05:00+00:00"},
        {"participant_id": "TEST_A", "score": 99, "total_profit": 1, "submitted_at": "2026-11-26T09:00:00+00:00"},
        {"participant_id": "test_b", "score": 99, "total_profit": 1, "submitted_at": "2026-11-26T09:00:00+00:00"},
        {"participant_id": "P3", "score": 90, "total_profit": 200, "submitted_at": "2026-11-26T10:20:00+00:00"},
        {"participant_id": "P4", "score": "90,0", "total_profit": 200, "submitted_at": "2026-11-26T10:10:00+00:00"},
        {"participant_id": "P5", "score": "", "total_profit": 300, "submitted_at": "2026-11-26T10:00:00+00:00"},
        {"participant_id": "P6", "score": 80, "total_profit": 300, "submitted_at": ""},
    ]
    ranked = game.ranking(rows)
    assert [r["participant_id"] for r in ranked] == ["P2", "P4", "P3", "P1"]
    assert [r["rank"] for r in ranked] == [1, 2, 3, 4]
    assert ranked[0]["score"] == 95.5
    assert game.ranking([]) == []


# --------------------------------------------------------------------------- #
# Pre-drawn sequences
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def draws():
    return game.load_sequences()


def test_sequences_load_complete(draws):
    assert set(draws) == set(cfg.BLOCKS) == {"C", "U"}
    for rows in draws.values():
        assert [r["round"] for r in rows] == list(range(1, cfg.ROUNDS_PER_BLOCK + 1))
        assert all(cfg.DEMAND_MIN <= r["demand"] <= cfg.DEMAND_MAX for r in rows)
        assert all(cfg.YIELD_MIN <= r["yield"] <= cfg.YIELD_MAX for r in rows)


def test_sequences_mean_criteria(draws):
    for block, rows in draws.items():
        mean_demand = sum(r["demand"] for r in rows) / len(rows)
        assert abs(mean_demand - 150) <= 15, block
        if game.is_uncertain(block):
            mean_yield = sum(r["yield"] for r in rows) / len(rows)
            assert abs(mean_yield - 0.70) <= 0.03 + 1e-9, block
        else:
            assert all(r["yield"] == 1.0 for r in rows)


def test_no_demand_value_repeats_across_blocks(draws):
    demands = [r["demand"] for rows in draws.values() for r in rows]
    assert len(demands) == len(set(demands)) == len(cfg.BLOCKS) * cfg.ROUNDS_PER_BLOCK
    assert min(demands) >= cfg.DEMAND_DRAW_MIN
    ordered = sorted(demands)
    assert all(b - a >= cfg.DEMAND_MIN_GAP for a, b in zip(ordered, ordered[1:]))


def test_uncertain_block_yields_not_repeated(draws):
    yields = [r["yield"] for r in draws["U"]]
    assert len(set(yields)) == cfg.ROUNDS_PER_BLOCK


def test_sequences_csv_is_reproducible(draws):
    seed, rows = make_sequences.find_seed()
    regenerated = {b: [(r["demand"], r["yield"]) for r in rows if r["block"] == b] for b in cfg.BLOCKS}
    on_disk = {b: [(r["demand"], r["yield"]) for r in rs] for b, rs in draws.items()}
    assert regenerated == on_disk


# --------------------------------------------------------------------------- #
# Group assignment
# --------------------------------------------------------------------------- #
def test_groups_and_supply_orders():
    assert cfg.GROUPS == {"H": {"margin": "high", "unit_cost": 3}, "L": {"margin": "low", "unit_cost": 9}}
    assert game.block_order("certain_first") == ["C", "U"]
    assert game.block_order("uncertain_first") == ["U", "C"]


def test_make_participants_blocks_of_2():
    rows = make_participants.make_assignment(40, supply_order="certain_first")
    assert [pid for pid, _, _ in rows][:3] == ["P001", "P002", "P003"]
    assert {o for _, _, o in rows} == {"certain_first"}
    groups = [g for _, g, _ in rows]
    for i in range(0, 40, 2):  # each consecutive pair contains H and L once
        assert sorted(groups[i:i + 2]) == ["H", "L"]
    assert groups[:2] != groups[2:4] or groups[2:4] != groups[4:6]  # order within pairs is random
    # Fixed seed: regenerating gives the same file; another seed gives another order.
    assert rows == make_participants.make_assignment(40, supply_order="certain_first")
    assert rows == make_participants.make_assignment(40, seed=cfg.ASSIGNMENT_SEED, supply_order="certain_first")
    assert groups != [g for _, g, _ in make_participants.make_assignment(40, seed=1, supply_order="certain_first")]


def test_make_participants_blocks_of_4_when_counterbalanced():
    rows = make_participants.make_assignment(40, supply_order="counterbalanced")
    cells = [(g, o) for _, g, o in rows]
    expected = sorted([("H", "certain_first"), ("H", "uncertain_first"), ("L", "certain_first"), ("L", "uncertain_first")])
    for i in range(0, 40, 4):
        assert sorted(cells[i:i + 4]) == expected
    assert Counter(cells) == {c: 10 for c in expected}


def test_make_participants_uneven_n():
    counts = Counter(g for _, g, _ in make_participants.make_assignment(11, supply_order="certain_first"))
    assert counts["H"] + counts["L"] == 11 and abs(counts["H"] - counts["L"]) == 1


def test_assignment_file_round_trip_and_precedence(tmp_path, monkeypatch):
    path = tmp_path / "assignment.csv"
    rows = make_participants.make_assignment(8, supply_order="counterbalanced")
    make_participants.write_assignment(rows, path=path)
    with pytest.raises(FileExistsError):
        make_participants.write_assignment(rows, path=path)
    assert path.read_text().splitlines()[0] == "participant_id,group,supply_order"
    mapping = game.load_assignment(path)
    assert mapping == {pid: {"group": g, "supply_order": o} for pid, g, o in rows}

    monkeypatch.setattr(cfg, "SUPPLY_ORDER", "counterbalanced")
    for pid, g, o in rows:
        assert game.assign(pid, mapping) == {"group": g, "supply_order": o}
    monkeypatch.setattr(cfg, "SUPPLY_ORDER", "certain_first")
    for pid, g, _ in rows:
        assert game.assign(pid, mapping) == {"group": g, "supply_order": "certain_first"}


def test_hash_fallback_is_stable_and_roughly_balanced():
    fallback = game.hash_assignment("X999")
    assert fallback == game.hash_assignment("X999") and fallback["group"] in cfg.GROUPS
    assert game.assign("X999", {}) == {"group": fallback["group"], "supply_order": "certain_first"}
    counts = Counter(game.hash_assignment(f"ID{i}")["group"] for i in range(2000))
    assert abs(counts["H"] - counts["L"]) < 150


def test_missing_assignment_file_is_empty(tmp_path):
    assert game.load_assignment(tmp_path / "nope.csv") == {}


def test_regenerated_assignment_csv_matches_generator():
    mapping = game.load_assignment()
    rows = make_participants.make_assignment(len(mapping))
    assert mapping == {pid: {"group": g, "supply_order": o} for pid, g, o in rows}


# --------------------------------------------------------------------------- #
# Analysis
# --------------------------------------------------------------------------- #
def _row(pid, group, orders: dict[str, int]):
    row = {"participant_id": pid, "group": group, "supply_order": "certain_first", "score": 0}
    row.update({code: 4 for code in scale.ITEM_CODES})
    row.update({"EC1": 7, "EC2": 7, "EC3": 1, "EC4": 1})
    for i, block in enumerate(["C", "U"]):
        row[f"{block}_position"] = i + 1
        for rnd in range(1, cfg.ROUNDS_PER_BLOCK + 1):
            row[f"{block}_r{rnd}_order"] = orders[block]
    return row


def test_analysis_measures():
    # H: optimal in C, anchored at mean demand (150) in U. L: anchored at 150 in both.
    df = pd.DataFrame([_row("P1", "H", {"C": 225, "U": 150}), _row("P2", "L", {"C": 150, "U": 150})])
    long = analysis.long_format(df)
    assert len(long) == 2 * 2 * cfg.ROUNDS_PER_BLOCK
    summary = analysis.block_summary(long).set_index(["participant_id", "block"])
    assert summary.loc[("P1", "C"), "q_star"] == 225 and summary.loc[("P2", "U"), "q_star"] == 101
    assert summary.loc[("P1", "C"), "abs_rel_error"] == 0
    assert summary.loc[("P1", "C"), "profit_share"] == pytest.approx(1)
    assert summary.loc[("P1", "C"), "anchoring_alpha"] == 0
    assert summary.loc[("P1", "U"), "anchoring_alpha"] == pytest.approx(1)
    assert summary.loc[("P1", "U"), "signed_rel_error"] == pytest.approx((150 - 303) / 303)
    assert summary.loc[("P2", "C"), "signed_rel_error"] == pytest.approx(1.0)
    assert summary.loc[("P2", "U"), "signed_rel_error"] == pytest.approx((150 - 101) / 101)

    scored = analysis.participant_summary(df, analysis.block_summary(long), long).set_index("participant_id")
    p1, p2 = scored.loc["P1"], scored.loc["P2"]
    assert (p1["group"], p2["group"]) == ("H", "L")
    assert p1["EC_mean"] == 4 and p1["PSC_mean"] == 4
    assert all(f"{c}_mean" in scored.columns for c in scale.CONSTRUCT_CODES)
    assert p1["penalty_abs_error"] == pytest.approx(153 / 303)
    assert p1["penalty_signed_error"] == pytest.approx(-153 / 303)
    share_u = game.profit_share(150, "U", "H")
    assert p1["penalty_profit_share"] == pytest.approx(1 - share_u)
    assert p1["score"] == round(100 * (1 + share_u) / 2, 1)  # stored 0 is replaced by the recomputed score
    assert p2["penalty_abs_error"] == pytest.approx(49 / 101 - 1)
    assert p2["score"] == game.score([("C", 150)] * 10 + [("U", 150)] * 10, "L")
