"""
Export / analysis step: turns the raw one-row-per-participant data into
analysis files. Nothing here is shown to participants.

Outputs (for input responses.csv):
    responses_scored.csv         one row per participant: raw row + score + construct means
                                 + per-block measures + supply-uncertainty penalties
    responses_long.csv           one row per participant x block x round
    responses_block_summary.csv  one row per participant x block (C, U)

Usage:
    python analysis.py data/responses.csv
    python analysis.py responses.csv -o out/        # e.g. a CSV downloaded from the Google Sheet

Measures (q* = optimal order of the block for the participant's group, Q = order):
    signed_rel_error      (Q − q*)/q*                         averaged over rounds
    abs_rel_error         |Q − q*|/q*                         averaged over rounds
    profit_share          E[π(Q)] / E[π(q*)]                  averaged over rounds
    anchoring_alpha       (q* − mean Q)/(q* − mean demand)    0 = optimal, 1 = anchored at mean demand
    score                 mean over all rounds of profit_share × 100, 1 decimal (game.score, as in the app)
    penalty_abs_error     abs_rel_error(U) − abs_rel_error(C)
    penalty_signed_error  signed_rel_error(U) − signed_rel_error(C)
    penalty_profit_share  profit_share(C) − profit_share(U)
    <construct>_mean      mean of the construct's items (EC_mean, EV_mean, ..., EPB_mean)
"""

import argparse
from pathlib import Path

import pandas as pd

import game
import survey_config as cfg
from scales import chen2022 as scale

MEAN_DEMAND = (cfg.DEMAND_MIN + cfg.DEMAND_MAX) / 2


def add_scale_scores(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of df with <construct>_mean for every construct whose items are all present.

    The attention check is never included. A mean is left empty if any of its items is missing.
    """
    out = df.copy()
    for construct, column in scale.MEAN_COLUMNS.items():
        codes = scale.item_codes(construct)
        if all(code in out.columns for code in codes):
            items = out[codes].apply(pd.to_numeric, errors="coerce")
            out[column] = items.mean(axis=1, skipna=False)
    return out


def long_format(df: pd.DataFrame) -> pd.DataFrame:
    """One row per participant x block x round (rounds without an order are skipped)."""
    records = []
    for _, row in df.iterrows():
        group = row.get("group")
        if group not in cfg.GROUPS:
            continue
        for block in cfg.BLOCKS:
            q_star, opt = game.optimal_order(block, group)
            for rnd in range(1, cfg.ROUNDS_PER_BLOCK + 1):
                prefix = game.round_key(block, rnd)
                order = pd.to_numeric(row.get(f"{prefix}_order"), errors="coerce")
                if pd.isna(order):
                    continue
                order = int(order)
                rec = {
                    "participant_id": row["participant_id"],
                    "group": group,
                    "unit_cost": game.unit_cost(group),
                    "supply_order": row.get("supply_order"),
                    "block": block,
                    "supply": cfg.BLOCKS[block]["supply"],
                    "position": row.get(f"{block}_position"),
                    "round": rnd,
                }
                for field in game.ROUND_FIELDS:
                    rec[field] = row.get(f"{prefix}_{field}")
                rec.update(
                    order=order,
                    q_star=q_star,
                    opt_expected_profit=opt,
                    expected_profit=game.expected_profit_of_order(order, block, group),
                    profit_share=game.profit_share(order, block, group),
                    signed_rel_error=(order - q_star) / q_star,
                    abs_rel_error=abs(order - q_star) / q_star,
                )
                records.append(rec)
    return pd.DataFrame(records)


def block_summary(long: pd.DataFrame) -> pd.DataFrame:
    """One row per participant x block."""
    if long.empty:
        return pd.DataFrame()
    keys = ["participant_id", "group", "supply_order", "block", "supply", "position", "q_star", "opt_expected_profit"]
    summary = (
        long.groupby(keys, dropna=False)
        .agg(
            n_rounds=("order", "size"),
            mean_order=("order", "mean"),
            signed_rel_error=("signed_rel_error", "mean"),
            abs_rel_error=("abs_rel_error", "mean"),
            profit_share=("profit_share", "mean"),
        )
        .reset_index()
    )
    summary["anchoring_alpha"] = (summary["q_star"] - summary["mean_order"]) / (summary["q_star"] - MEAN_DEMAND)
    return summary


def scores(long: pd.DataFrame) -> pd.DataFrame:
    """participant_id, score (same function as the app: game.score)."""
    if long.empty:
        return pd.DataFrame(columns=["participant_id", "score"])
    return pd.DataFrame(
        [
            {"participant_id": pid, "score": game.score(zip(g["block"], g["order"]), g["group"].iloc[0])}
            for pid, g in long.groupby("participant_id", sort=False)
        ]
    )


def participant_summary(df: pd.DataFrame, summary: pd.DataFrame, long: pd.DataFrame | None = None) -> pd.DataFrame:
    """Raw rows + construct means + score + per-block measures + supply-uncertainty penalties.

    `score` is recomputed from the orders with game.score (it equals the stored column).
    """
    out = add_scale_scores(df)
    if long is not None and not long.empty:
        out = out.drop(columns=["score"], errors="ignore").merge(scores(long), on="participant_id", how="left")
    if summary.empty:
        return out
    measures = ["signed_rel_error", "abs_rel_error", "profit_share", "anchoring_alpha"]
    wide = summary.pivot(index="participant_id", columns="block", values=measures)
    wide.columns = [f"{block}_{measure}" for measure, block in wide.columns]
    wide = wide.reindex(columns=[f"{b}_{m}" for b in cfg.BLOCKS for m in measures])  # both blocks, always
    wide["penalty_abs_error"] = wide["U_abs_rel_error"] - wide["C_abs_rel_error"]
    wide["penalty_signed_error"] = wide["U_signed_rel_error"] - wide["C_signed_rel_error"]
    wide["penalty_profit_share"] = wide["C_profit_share"] - wide["U_profit_share"]
    return out.merge(wide.reset_index(), on="participant_id", how="left")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input", type=Path, help="CSV with one row per participant")
    parser.add_argument("-o", "--outdir", type=Path, help="output folder (default: next to the input)")
    args = parser.parse_args()

    outdir = args.outdir or args.input.parent
    outdir.mkdir(parents=True, exist_ok=True)
    stem = args.input.stem
    df = pd.read_csv(args.input)
    long = long_format(df)
    summary = block_summary(long)
    scored = participant_summary(df, summary, long)

    for suffix, frame in [("scored", scored), ("long", long), ("block_summary", summary)]:
        path = outdir / f"{stem}_{suffix}.csv"
        frame.to_csv(path, index=False)
        print(f"Wrote {len(frame)} rows to {path}")


if __name__ == "__main__":
    main()
