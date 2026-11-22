"""
Generate the pre-drawn demand / yield values once and write sequences.csv.

Everyone sees the same draws. Draws belong to the block (CH, CL, UH, UL), not
to the position in the participant's sequence.

- One set of ROUNDS_PER_BLOCK demand values is used in all 4 blocks, in a
  different order per block, so certain-vs-uncertain comparisons are not
  driven by demand luck.
- One set of yield values is used for UH and UL, in different orders.
  Certain blocks get yield 1.00 (every widget usable).
- Starting from SEQUENCE_SEED_START, the first seed whose block means meet the
  criteria (demand 150 ± 15, yield 0.70 ± 0.03) is used.

Usage:  python make_sequences.py            # writes sequences.csv
"""

import csv
import random

import game
import survey_config as cfg

DEMAND_MEAN = (cfg.DEMAND_MIN + cfg.DEMAND_MAX) / 2
YIELD_MEAN = (cfg.YIELD_MIN + cfg.YIELD_MAX) / 2


def _distinct_orders(rng: random.Random, values: list, k: int) -> list[list] | None:
    """k orderings of values that are pairwise different (None if values don't allow it)."""
    orders: list[list] = []
    for _ in range(1000):
        candidate = values[:]
        rng.shuffle(candidate)
        if candidate not in orders:
            orders.append(candidate)
            if len(orders) == k:
                return orders
    return None


def generate(seed: int) -> list[dict] | None:
    """Rows (block, round, demand, yield) for this seed, or None if no distinct orders exist."""
    rng = random.Random(seed)
    n = cfg.ROUNDS_PER_BLOCK
    demands = [rng.randint(cfg.DEMAND_MIN, cfg.DEMAND_MAX) for _ in range(n)]
    lo, hi = round(cfg.YIELD_MIN * 100), round(cfg.YIELD_MAX * 100)
    yields = [rng.randint(lo, hi) / 100 for _ in range(n)]  # uniform on 0.40, 0.41, ..., 1.00

    blocks = list(cfg.BLOCKS)
    uncertain = [b for b in blocks if game.is_uncertain(b)]
    demand_orders = _distinct_orders(rng, demands, len(blocks))
    yield_orders = _distinct_orders(rng, yields, len(uncertain))
    if demand_orders is None or yield_orders is None:
        return None
    yield_by_block = dict(zip(uncertain, yield_orders))

    rows = []
    for block, block_demands in zip(blocks, demand_orders):
        block_yields = yield_by_block.get(block, [1.0] * n)
        for i in range(n):
            rows.append({"block": block, "round": i + 1, "demand": block_demands[i], "yield": block_yields[i]})
    return rows


def block_means(rows: list[dict]) -> dict[str, dict]:
    means = {}
    for block in cfg.BLOCKS:
        r = [x for x in rows if x["block"] == block]
        means[block] = {
            "demand": sum(x["demand"] for x in r) / len(r),
            "yield": sum(x["yield"] for x in r) / len(r),
        }
    return means


def meets_criteria(rows: list[dict]) -> bool:
    for block, m in block_means(rows).items():
        if abs(m["demand"] - DEMAND_MEAN) > cfg.DEMAND_MEAN_TOLERANCE:
            return False
        if game.is_uncertain(block) and abs(m["yield"] - YIELD_MEAN) > cfg.YIELD_MEAN_TOLERANCE + 1e-9:
            return False
    return True


def find_seed(start: int = cfg.SEQUENCE_SEED_START, max_tries: int = 100_000) -> tuple[int, list[dict]]:
    for seed in range(start, start + max_tries):
        rows = generate(seed)
        if rows is not None and meets_criteria(rows):
            return seed, rows
    raise RuntimeError("No seed met the criteria; widen the tolerances.")


def write_csv(rows: list[dict], path=None) -> None:
    path = game.ROOT / (path or cfg.SEQUENCES_FILE)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["block", "round", "demand", "yield"])
        writer.writeheader()
        for row in rows:
            writer.writerow({**row, "yield": f"{row['yield']:.2f}"})


def main() -> None:
    seed, rows = find_seed()
    write_csv(rows)
    print(f"Chosen seed: {seed}")
    for block, m in block_means(rows).items():
        print(f"  {block}: mean demand {m['demand']:.1f}, mean yield {m['yield']:.3f}")
    print(f"Wrote {len(rows)} rows to {cfg.SEQUENCES_FILE}")


if __name__ == "__main__":
    main()
