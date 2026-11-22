"""
Generate the pre-drawn demand / yield values once and write sequences.csv.

Everyone sees the same draws. Draws belong to the block (CH, CL, UH, UL), not
to the position in the participant's sequence.

- Each block gets its own ROUNDS_PER_BLOCK demand values. No demand value
  appears in more than one block, so participants cannot learn a repeating
  set of numbers across blocks.
- Each uncertain block (UH, UL) gets its own yield values, again with no value
  shared between the two. Certain blocks get yield 1.00 (every widget usable).
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


def _draw_unique(rng: random.Random, lo: int, hi: int, n: int, used: set[int]) -> list[int]:
    """n integers uniform on [lo, hi], none of them already in `used` (redrawn if so)."""
    values: list[int] = []
    while len(values) < n:
        v = rng.randint(lo, hi)
        if v not in used:
            used.add(v)
            values.append(v)
    return values


def generate(seed: int) -> list[dict]:
    """Rows (block, round, demand, yield) for this seed: independent draws per block."""
    rng = random.Random(seed)
    n = cfg.ROUNDS_PER_BLOCK
    lo, hi = round(cfg.YIELD_MIN * 100), round(cfg.YIELD_MAX * 100)
    used_demands: set[int] = set()
    used_yields: set[int] = set()  # in percent
    rows = []
    for block in cfg.BLOCKS:
        demands = _draw_unique(rng, cfg.DEMAND_MIN, cfg.DEMAND_MAX, n, used_demands)
        if game.is_uncertain(block):
            yields = [y / 100 for y in _draw_unique(rng, lo, hi, n, used_yields)]  # 0.40, 0.41, ..., 1.00
        else:
            yields = [1.0] * n
        for i in range(n):
            rows.append({"block": block, "round": i + 1, "demand": demands[i], "yield": yields[i]})
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
        if meets_criteria(rows):
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
