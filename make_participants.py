"""
Create participant IDs (P001, P002, ...) spread evenly across S1–S4, write
assignment.csv, and print each participant's link.

IDs are assigned in shuffled groups of 4, each containing every sequence once.
So the sequences are balanced exactly when N is a multiple of 4, differ by at
most 1 otherwise, and stay balanced if you hand out the IDs in order and not
all of them get used.

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

import game
import survey_config as cfg


def make_assignment(n: int, seed: int | None = None) -> list[tuple[str, str]]:
    rng = random.Random(seed)
    names = list(cfg.SEQUENCES)
    sequences: list[str] = []
    while len(sequences) < n:
        group = names[:]
        rng.shuffle(group)
        sequences.extend(group)
    width = max(3, len(str(n)))
    return [(f"P{i:0{width}d}", seq) for i, seq in enumerate(sequences[:n], start=1)]


def write_assignment(rows: list[tuple[str, str]], path=None, force: bool = False) -> None:
    path = game.ROOT / (path or cfg.ASSIGNMENT_FILE)
    if path.exists() and not force:
        raise FileExistsError(
            f"{path.name} already exists. IDs from it may already be handed out; "
            "use --force to overwrite it."
        )
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["participant_id", "sequence"])
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("n", type=int, help="number of participants")
    parser.add_argument("--base-url", default=cfg.BASE_URL, help=f"app URL (default: {cfg.BASE_URL})")
    parser.add_argument("--seed", type=int, default=None, help="shuffle seed (default: random)")
    parser.add_argument("--force", action="store_true", help="overwrite an existing assignment file")
    args = parser.parse_args()

    rows = make_assignment(args.n, args.seed)
    try:
        write_assignment(rows, force=args.force)
    except FileExistsError as exc:
        sys.exit(str(exc))

    base = args.base_url.rstrip("/")
    for pid, seq in rows:
        print(f"{pid}\t{seq}\t{base}/?pid={pid}")
    counts = {s: sum(1 for _, x in rows if x == s) for s in cfg.SEQUENCES}
    print(f"\nWrote {len(rows)} IDs to {cfg.ASSIGNMENT_FILE}: " + ", ".join(f"{s}={c}" for s, c in counts.items()))


if __name__ == "__main__":
    main()
