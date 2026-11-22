from collections import Counter

import pandas as pd
import pytest

import analysis
import game
import make_participants
import make_sequences
import survey_config as cfg


# --------------------------------------------------------------------------- #
# Profit function and rounding
# --------------------------------------------------------------------------- #
def test_worked_example_profit_240():
    # Unit cost 9, uncertain supply: order 150, 120 usable (Z = 0.80), demand 110.
    r = game.round_outcome(order=150, demand=110, yield_=0.80, cost=9)
    assert r == {
        "order": 150, "usable": 120, "demand": 110, "sales": 110,
        "revenue": 1320, "cost": 1080, "leftover": 10, "profit": 240,
    }


def test_comprehension_q2_profit_660():
    r = game.round_outcome(order=100, demand=80, yield_=None, cost=3)
    assert r["profit"] == 660
    assert cfg.COMPREHENSION[1]["answer"] == 660


def test_comprehension_q1_usable_120():
    assert game.usable_units(200, 0.60) == 120
    assert cfg.COMPREHENSION[0]["answer"] == 120


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
EXPECTED_OPTIMA = {"CH": (225, 1012.5), "CL": (75, 112.5), "UH": (303, 954.0), "UL": (101, 106.0)}


@pytest.mark.parametrize("block", list(EXPECTED_OPTIMA))
def test_argmax_expected_profit(block):
    q_star, e_star = game.optimal_order(block)
    exp_q, exp_e = EXPECTED_OPTIMA[block]
    assert q_star == exp_q == cfg.OPTIMAL_ORDERS[block]
    assert abs(e_star - exp_e) <= 2
    assert abs(e_star - cfg.OPTIMAL_EXPECTED_PROFIT[block]) <= 2


def test_expected_profit_certain_closed_form():
    # 12 * (225 - 225^2/600) - 3 * 225
    assert float(game.expected_profit(225, "CH")) == pytest.approx(1012.5)
    assert float(game.expected_profit(400, "CH")) == pytest.approx(12 * 150 - 3 * 400)


# --------------------------------------------------------------------------- #
# Pre-drawn sequences
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def draws():
    return game.load_sequences()


def test_sequences_load_complete(draws):
    assert set(draws) == set(cfg.BLOCKS)
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


def test_uncertain_blocks_have_their_own_yields(draws):
    uh, ul = [r["yield"] for r in draws["UH"]], [r["yield"] for r in draws["UL"]]
    assert len(set(uh) | set(ul)) == 2 * cfg.ROUNDS_PER_BLOCK


def test_sequences_csv_is_reproducible(draws):
    seed, rows = make_sequences.find_seed()
    regenerated = {b: [(r["demand"], r["yield"]) for r in rows if r["block"] == b] for b in cfg.BLOCKS}
    on_disk = {b: [(r["demand"], r["yield"]) for r in rs] for b, rs in draws.items()}
    assert regenerated == on_disk


# --------------------------------------------------------------------------- #
# Counterbalancing and assignment
# --------------------------------------------------------------------------- #
def test_sequence_definitions():
    assert cfg.SEQUENCES == {
        "S1": ["CH", "CL", "UH", "UL"],
        "S2": ["CL", "CH", "UL", "UH"],
        "S3": ["UH", "UL", "CH", "CL"],
        "S4": ["UL", "UH", "CL", "CH"],
    }
    assert game.sequence_info("S1") == {"supply_order": "certain_first", "margin_order": "high_first"}
    assert game.sequence_info("S4") == {"supply_order": "uncertain_first", "margin_order": "low_first"}


def test_make_participants_balances_exactly():
    rows = make_participants.make_assignment(40, seed=1)
    assert [pid for pid, _ in rows][:3] == ["P001", "P002", "P003"]
    assert Counter(s for _, s in rows) == {"S1": 10, "S2": 10, "S3": 10, "S4": 10}
    # Balanced at every multiple of 4 when handed out in order.
    for k in range(4, 41, 4):
        assert set(Counter(s for _, s in rows[:k]).values()) == {k // 4}
    assert [s for _, s in rows] != [s for _, s in make_participants.make_assignment(40, seed=2)]


def test_make_participants_uneven_n():
    counts = Counter(s for _, s in make_participants.make_assignment(10, seed=3))
    assert max(counts.values()) - min(counts.values()) <= 1 and sum(counts.values()) == 10


def test_assignment_file_round_trip_and_precedence(tmp_path):
    path = tmp_path / "assignment.csv"
    rows = make_participants.make_assignment(8, seed=4)
    make_participants.write_assignment(rows, path=path)
    with pytest.raises(FileExistsError):
        make_participants.write_assignment(rows, path=path)
    mapping = game.load_assignment(path)
    assert mapping == dict(rows)
    pid, seq = rows[0]
    assert game.assign_sequence(pid, mapping) == seq
    # Not listed -> stable hash fallback
    assert game.assign_sequence("X999", mapping) == game.hash_sequence("X999") in cfg.SEQUENCES


def test_missing_assignment_file_is_empty(tmp_path):
    assert game.load_assignment(tmp_path / "nope.csv") == {}


# --------------------------------------------------------------------------- #
# Analysis
# --------------------------------------------------------------------------- #
def _row(pid, orders: dict[str, int]):
    row = {"participant_id": pid, "sequence": "S1", "EC1": 4, "EC2": 4, "EC3": 2, "EC4": 2}
    for i, block in enumerate(cfg.SEQUENCES["S1"]):
        row[f"{block}_position"] = i + 1
        for rnd in range(1, cfg.ROUNDS_PER_BLOCK + 1):
            row[f"{block}_r{rnd}_order"] = orders[block]
    return row


def test_analysis_measures():
    # Optimal in CH and CL, anchored at mean demand (150) in UH and UL.
    df = pd.DataFrame([_row("P1", {"CH": 225, "CL": 75, "UH": 150, "UL": 150})])
    long = analysis.long_format(df)
    assert len(long) == 4 * cfg.ROUNDS_PER_BLOCK
    summary = analysis.block_summary(long).set_index("block")
    assert summary.loc["CH", "abs_rel_error"] == 0
    assert summary.loc["CH", "profit_share"] == pytest.approx(1)
    assert summary.loc["CH", "anchoring_alpha"] == 0
    assert summary.loc["UH", "anchoring_alpha"] == pytest.approx(1)
    assert summary.loc["UH", "signed_rel_error"] == pytest.approx((150 - 303) / 303)
    assert summary.loc["UL", "signed_rel_error"] == pytest.approx((150 - 101) / 101)
    assert summary.loc["UH", "profit_share"] < 1

    scored = analysis.participant_summary(df, analysis.block_summary(long)).iloc[0]
    assert scored["EC_mean"] == 3
    assert scored["penalty_abs_error_high"] == pytest.approx(153 / 303)
    assert scored["penalty_signed_error_high"] == pytest.approx(-153 / 303)
    assert scored["penalty_abs_error_low"] == pytest.approx(49 / 101)
    assert scored["penalty_signed_error_low"] == pytest.approx(49 / 101)
