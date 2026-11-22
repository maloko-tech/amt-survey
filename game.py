"""
Newsvendor "widget selling game" logic (after Käki, Liesiö, Salo & Talluri, 2015).

Pure Python (no Streamlit), shared by the app, the scripts, analysis.py and the
tests. All parameters come from survey_config.py.
"""

import csv
import hashlib
from decimal import ROUND_HALF_UP, Decimal
from functools import lru_cache
from pathlib import Path

import numpy as np

import survey_config as cfg

ROOT = Path(__file__).resolve().parent
ROUND_FIELDS = ["order", "usable", "demand", "yield", "sales", "profit", "seconds"]


# --------------------------------------------------------------------------- #
# Blocks
# --------------------------------------------------------------------------- #
def unit_cost(block: str) -> int:
    return cfg.UNIT_COST[cfg.BLOCKS[block]["margin"]]


def is_uncertain(block: str) -> bool:
    return cfg.BLOCKS[block]["supply"] == "uncertain"


def round_key(block: str, rnd: int) -> str:
    return f"{block}_r{rnd}"


def sequence_info(sequence: str) -> dict:
    """supply_order / margin_order labels for a sequence like S3."""
    first = cfg.SEQUENCES[sequence][0]
    return {
        "supply_order": f"{cfg.BLOCKS[first]['supply']}_first",
        "margin_order": f"{cfg.BLOCKS[first]['margin']}_first",
    }


# --------------------------------------------------------------------------- #
# One round
# --------------------------------------------------------------------------- #
def usable_units(order: int, yield_: float | None) -> int:
    """Usable widgets = round_half_up(Z × order); all of them if supply is certain (yield None)."""
    if yield_ is None:
        return int(order)
    exact = Decimal(str(yield_)) * int(order)  # Decimal avoids 0.7 * 15 = 10.4999...
    return int(exact.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def round_outcome(order: int, demand: int, yield_: float | None, cost: int) -> dict:
    """Outcome of one round. Unit cost is paid only for usable widgets."""
    usable = usable_units(order, yield_)
    sales = min(int(demand), usable)
    revenue = cfg.PRICE * sales
    cost_total = cost * usable
    leftover = usable - sales
    profit = revenue + cfg.SALVAGE * leftover - cost_total
    return {
        "order": int(order),
        "usable": usable,
        "demand": int(demand),
        "sales": sales,
        "revenue": revenue,
        "cost": cost_total,
        "leftover": leftover,
        "profit": profit,
    }


# --------------------------------------------------------------------------- #
# Expected profit and optimal order (for analysis and tests)
# --------------------------------------------------------------------------- #
_YIELD_GRID_POINTS = 4000


def expected_sales(x):
    """m(x) = E[min(D, x)] for D ~ U[DEMAND_MIN=0, DEMAND_MAX]: x − x²/(2·Dmax) for x ≤ Dmax, else Dmax/2."""
    dmax = cfg.DEMAND_MAX
    x = np.asarray(x, dtype=float)
    return np.where(x <= dmax, x - x**2 / (2 * dmax), dmax / 2)


def _profit_given_quantity(x, cost):
    m = expected_sales(x)
    return cfg.PRICE * m + cfg.SALVAGE * (x - m) - cost * x


def expected_profit(q, block: str):
    """E[π(q)] = E_Z[p·m(Z·q) − c·Z·q]; Z = 1 (certain) or U[YIELD_MIN, YIELD_MAX] (midpoint rule)."""
    q = np.asarray(q, dtype=float)
    cost = unit_cost(block)
    if not is_uncertain(block):
        return _profit_given_quantity(q, cost)
    n = _YIELD_GRID_POINTS
    z = cfg.YIELD_MIN + (cfg.YIELD_MAX - cfg.YIELD_MIN) * (np.arange(n) + 0.5) / n
    x = np.multiply.outer(q, z)
    return _profit_given_quantity(x, cost).mean(axis=-1)


@lru_cache(maxsize=None)
def expected_profit_table(block: str) -> np.ndarray:
    """E[π(q)] for every integer order q = 0 … ORDER_MAX (index = q)."""
    return expected_profit(np.arange(cfg.ORDER_MIN, cfg.ORDER_MAX + 1), block)


@lru_cache(maxsize=None)
def optimal_order(block: str) -> tuple[int, float]:
    """(q*, E[π(q*)]) over integer orders."""
    table = expected_profit_table(block)
    i = int(np.argmax(table))
    return cfg.ORDER_MIN + i, float(table[i])


# --------------------------------------------------------------------------- #
# Pre-drawn demand / yield sequences
# --------------------------------------------------------------------------- #
def load_sequences(path: str | Path | None = None) -> dict[str, list[dict]]:
    """{block: [{"round", "demand", "yield"}, ...]} from sequences.csv, validated."""
    path = ROOT / (path or cfg.SEQUENCES_FILE)
    draws: dict[str, list[dict]] = {b: [] for b in cfg.BLOCKS}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            draws[row["block"]].append(
                {"round": int(row["round"]), "demand": int(row["demand"]), "yield": float(row["yield"])}
            )
    for block, rows in draws.items():
        rows.sort(key=lambda r: r["round"])
        rounds = [r["round"] for r in rows]
        if rounds != list(range(1, cfg.ROUNDS_PER_BLOCK + 1)):
            raise ValueError(
                f"{path.name}: block {block} has rounds {rounds}, expected 1..{cfg.ROUNDS_PER_BLOCK}. "
                "Re-run make_sequences.py after changing ROUNDS_PER_BLOCK."
            )
    return draws


# --------------------------------------------------------------------------- #
# Assignment to counterbalancing sequences
# --------------------------------------------------------------------------- #
def load_assignment(path: str | Path | None = None) -> dict[str, str]:
    """{participant_id: sequence} from assignment.csv, or {} if the file doesn't exist."""
    path = ROOT / (path or cfg.ASSIGNMENT_FILE)
    if not path.exists():
        return {}
    with open(path, newline="", encoding="utf-8") as f:
        mapping = {row["participant_id"].strip(): row["sequence"].strip() for row in csv.DictReader(f)}
    unknown = set(mapping.values()) - set(cfg.SEQUENCES)
    if unknown:
        raise ValueError(f"{path.name} contains unknown sequences: {sorted(unknown)}")
    return mapping


def hash_sequence(pid: str) -> str:
    names = sorted(cfg.SEQUENCES)
    digest = hashlib.sha256(f"{cfg.ASSIGNMENT_SALT}:{pid}".encode()).digest()
    return names[int.from_bytes(digest[:8], "big") % len(names)]


def assign_sequence(pid: str, assignment: dict[str, str] | None = None) -> str:
    """assignment.csv takes precedence; otherwise a stable hash of pid + salt."""
    if assignment is None:
        assignment = load_assignment()
    return assignment.get(pid) or hash_sequence(pid)
