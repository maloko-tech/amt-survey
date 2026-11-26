"""
Create participant IDs (P001, P002, ...), assign them to the groups H (high
margin) and L (low margin), write assignment.csv, and print each link.

Assignment uses permuted blocks with a fixed seed (ASSIGNMENT_SEED):
- SUPPLY_ORDER = "certain_first": blocks of 2. Each consecutive pair of IDs
  (P001-P002, P003-P004, ...) contains H and L once, in random order.
- SUPPLY_ORDER = "counterbalanced": blocks of 4 over group x supply order. Each
  consecutive group of 4 IDs contains H/certain_first, H/uncertain_first,
  L/certain_first and L/uncertain_first once, in random order.
So the cells stay balanced if you hand out the IDs in order and not all of
them get used.

Usage:
    python make_participants.py 40
    python make_participants.py 40 --base-url https://your-app.streamlit.app --seed 1
    python make_participants.py 40 --force      # overwrite an existing assignment.csv

assignment.csv must be deployed together with the app: it takes precedence
over the hash-based assignment.
"""


import argparse
import csv
import random
import sys
from collections import Counter

import game
import survey_config as cfg


def cells(supply_order: str | None = None) -> list[tuple[str, str]]:
    """The (group, supply_order) cells that each permuted block contains once."""
    supply_order = supply_order or cfg.SUPPLY_ORDER
    orders = list(cfg.SUPPLY_ORDERS) if supply_order == "counterbalanced" else ["certain_first"]
    return [(g, o) for g in cfg.GROUPS for o in orders]


def make_assignment(
    n: int, seed: int | None = None, supply_order: str | None = None
) -> list[tuple[str, str, str]]:
    """[(participant_id, group, supply_order), ...] in permuted blocks of len(cells())."""
    rng = random.Random(cfg.ASSIGNMENT_SEED if seed is None else seed)
    block = cells(supply_order)
    assigned: list[tuple[str, str]] = []
    while len(assigned) < n:
        permuted = block[:]
        rng.shuffle(permuted)
        assigned.extend(permuted)
    width = max(3, len(str(n)))
    return [(f"P{i:0{width}d}", g, o) for i, (g, o) in enumerate(assigned[:n], start=1)]


def write_assignment(rows: list[tuple[str, str, str]], path=None, force: bool = False) -> None:
    path = game.ROOT / (path or cfg.ASSIGNMENT_FILE)
    if path.exists() and not force:
        raise FileExistsError(
            f"{path.name} already exists. IDs from it may already be handed out; "
            "use --force to overwrite it."
        )
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["participant_id", "group", "supply_order"])
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("n", type=int, help="number of participants")
    parser.add_argument("--base-url", default=cfg.BASE_URL, help=f"app URL (default: {cfg.BASE_URL})")
    parser.add_argument(
        "--seed", type=int, default=cfg.ASSIGNMENT_SEED, help=f"shuffle seed (default: {cfg.ASSIGNMENT_SEED})"
    )
    parser.add_argument("--force", action="store_true", help="overwrite an existing assignment file")
    args = parser.parse_args()

    rows = make_assignment(args.n, args.seed)
    try:
        write_assignment(rows, force=args.force)
    except FileExistsError as exc:
        sys.exit(str(exc))

    base = args.base_url.rstrip("/")
    for pid, group, order in rows:
        print(f"{pid}\t{group}\t{order}\t{base}/?pid={pid}")
    counts = Counter((g, o) for _, g, o in rows)
    summary = ", ".join(f"{g}/{o}={c}" for (g, o), c in sorted(counts.items()))
    print(f"\nWrote {len(rows)} IDs to {cfg.ASSIGNMENT_FILE} (SUPPLY_ORDER={cfg.SUPPLY_ORDER}, seed {args.seed}): {summary}")


if __name__ == "__main__":
    main()
