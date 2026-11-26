"""
Newsvendor "widget selling game" logic (after Käki, Liesiö, Salo & Talluri, 2015).

Pure Python (no Streamlit), shared by the app, the scripts, analysis.py and the
tests. All parameters come from survey_config.py.
"""

import csv
import hashlib
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from functools import lru_cache
from pathlib import Path

import numpy as np

import survey_config as cfg

ROOT = Path(__file__).resolve().parent
ROUND_FIELDS = ["order", "usable", "demand", "yield", "sales", "profit", "seconds"]

assert cfg.SUPPLY_ORDER in ("certain_first", "counterbalanced"), "SUPPLY_ORDER must be certain_first or counterbalanced"


# --------------------------------------------------------------------------- #
# Groups and blocks
# --------------------------------------------------------------------------- #
def unit_cost(group: str) -> int:
    return cfg.GROUPS[group]["unit_cost"]


def is_uncertain(block: str) -> bool:
    return cfg.BLOCKS[block]["supply"] == "uncertain"


def round_key(block: str, rnd: int) -> str:
    return f"{block}_r{rnd}"


def block_order(supply_order: str) -> list[str]:
    """["C", "U"] or ["U", "C"]."""
    return cfg.SUPPLY_ORDERS[supply_order]


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
# Expected profit, optimal order and score (shared by the app, analysis and tests)
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


def expected_profit(q, block: str, group: str):
    """E[π(q)] = E_Z[p·m(Z·q) − c·Z·q]; Z = 1 (certain) or U[YIELD_MIN, YIELD_MAX] (midpoint rule)."""
    q = np.asarray(q, dtype=float)
    cost = unit_cost(group)
    if not is_uncertain(block):
        return _profit_given_quantity(q, cost)
    n = _YIELD_GRID_POINTS
    z = cfg.YIELD_MIN + (cfg.YIELD_MAX - cfg.YIELD_MIN) * (np.arange(n) + 0.5) / n
    x = np.multiply.outer(q, z)
    return _profit_given_quantity(x, cost).mean(axis=-1)


@lru_cache(maxsize=None)
def expected_profit_table(block: str, group: str) -> np.ndarray:
    """E[π(q)] for every integer order q = ORDER_MIN … ORDER_MAX (index = q − ORDER_MIN)."""
    return expected_profit(np.arange(cfg.ORDER_MIN, cfg.ORDER_MAX + 1), block, group)


@lru_cache(maxsize=None)
def optimal_order(block: str, group: str) -> tuple[int, float]:
    """(q*, E[π(q*)]) over integer orders."""
    table = expected_profit_table(block, group)
    i = int(np.argmax(table))
    return cfg.ORDER_MIN + i, float(table[i])


def expected_profit_of_order(order: int, block: str, group: str) -> float:
    return float(expected_profit_table(block, group)[int(order) - cfg.ORDER_MIN])


def profit_share(order: int, block: str, group: str) -> float:
    """E[π(Q)] / E[π(q*)] for one round (1 = optimal; can be negative for very large orders)."""
    return expected_profit_of_order(order, block, group) / optimal_order(block, group)[1]


def score(orders, group: str) -> float | None:
    """Mean over rounds of E[π(Q_t)] / E[π(q*)] × 100, rounded to 1 decimal.

    orders: iterable of (block, order) pairs, one per round played. None if there are none.
    """
    shares = [profit_share(order, block, group) for block, order in orders]
    if not shares:
        return None
    return round(100 * sum(shares) / len(shares), 1)


def ranking(rows: list[dict]) -> list[dict]:
    """Completed, non-test rows ranked by score (desc), then total_profit (desc), then submitted_at (asc).

    rows: dicts as stored in the Sheet (values may be strings). Rows without a
    numeric score or a submitted_at, and IDs starting with TEST_ID_PREFIX, are left out.
    Returns [{"rank", "participant_id", "score", "total_profit", "submitted_at"}, ...].
    """
    def number(value):
        try:
            return float(str(value).replace(",", "."))
        except (TypeError, ValueError):
            return None

    entries = []
    for row in rows:
        pid = str(row.get("participant_id", "")).strip()
        s = number(row.get("score"))
        submitted = str(row.get("submitted_at", "") or "").strip()
        if not pid or pid.upper().startswith(cfg.TEST_ID_PREFIX.upper()) or s is None or not submitted:
            continue
        try:
            when = datetime.fromisoformat(submitted)
        except ValueError:
            continue
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        profit = number(row.get("total_profit")) or 0.0
        entries.append({"participant_id": pid, "score": s, "total_profit": profit, "submitted_at": submitted,
                        "_when": when})
    entries.sort(key=lambda e: (-e["score"], -e["total_profit"], e["_when"]))
    ranked = []
    for i, e in enumerate(entries, start=1):
        e.pop("_when")
        ranked.append({"rank": i, **e})
    return ranked


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
# Assignment to groups (and supply order)
# --------------------------------------------------------------------------- #
def load_assignment(path: str | Path | None = None) -> dict[str, dict]:
    """{participant_id: {"group", "supply_order"}} from assignment.csv, or {} if the file doesn't exist."""
    path = ROOT / (path or cfg.ASSIGNMENT_FILE)
    if not path.exists():
        return {}
    with open(path, newline="", encoding="utf-8") as f:
        mapping = {
            row["participant_id"].strip(): {
                "group": row["group"].strip(),
                "supply_order": (row.get("supply_order") or "certain_first").strip(),
            }
            for row in csv.DictReader(f)
        }
    groups = {a["group"] for a in mapping.values()}
    orders = {a["supply_order"] for a in mapping.values()}
    unknown = (groups - set(cfg.GROUPS)) | (orders - set(cfg.SUPPLY_ORDERS))
    if unknown:
        raise ValueError(f"{path.name} contains unknown groups or supply orders: {sorted(unknown)}")
    return mapping


def _hash_int(pid: str) -> int:
    digest = hashlib.sha256(f"{cfg.ASSIGNMENT_SALT}:{pid}".encode()).digest()
    return int.from_bytes(digest[:8], "big")


def hash_assignment(pid: str) -> dict:
    """Fallback: group = hash(pid + salt) mod 2; with counterbalancing, the next bit picks the supply order."""
    h = _hash_int(pid)
    groups, orders = sorted(cfg.GROUPS), list(cfg.SUPPLY_ORDERS)
    return {"group": groups[h % len(groups)], "supply_order": orders[(h // len(groups)) % len(orders)]}


def assign(pid: str, assignment: dict[str, dict] | None = None) -> dict:
    """{"group", "supply_order"}: assignment.csv takes precedence; otherwise a stable hash of pid + salt.

    With SUPPLY_ORDER = "certain_first", everyone plays C then U whatever the file says.
    """
    if assignment is None:
        assignment = load_assignment()
    result = dict(assignment.get(pid) or hash_assignment(pid))
    if cfg.SUPPLY_ORDER != "counterbalanced":
        result["supply_order"] = "certain_first"
    return result
