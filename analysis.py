"""
Export / analysis step: turns the raw one-row-per-participant data into
analysis files. Nothing here is shown to participants.

Outputs (for input responses.csv):
    responses_scored.csv         one row per participant: raw row + EC_mean
                                 + per-block errors + supply-uncertainty penalties
    responses_long.csv           one row per participant x block x round
    responses_block_summary.csv  one row per participant x block

Usage:
    python analysis.py data/responses.csv
    python analysis.py responses.csv -o out/        # e.g. a CSV downloaded from the Google Sheet

Measures (q* = optimal order of the block, Q = order):
    signed_rel_error  (Q − q*)/q*                         averaged over rounds
    abs_rel_error     |Q − q*|/q*                         averaged over rounds
    profit_share      E[π(Q)] / E[π(q*)]                  averaged over rounds
    anchoring_alpha   (q* − mean Q)/(q* − mean demand)    0 = optimal, 1 = anchored at mean demand
    penalty_*         error(uncertain) − error(certain), per margin (high: UH − CH, low: UL − CL)
"""

import argparse
from pathlib import Path

import pandas as pd

import game
import survey_config as cfg
from scales import environmental_concern as ec

MEAN_DEMAND = (cfg.DEMAND_MIN + cfg.DEMAND_MAX) / 2


def add_scale_scores(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of df with EC_mean = mean of EC1-EC4 (attention check excluded).

    EC_mean is left empty if any item is missing.
    """
    out = df.copy()
    if all(code in out.columns for code in ec.ITEM_CODES):
        items = out[ec.ITEM_CODES].apply(pd.to_numeric, errors="coerce")
        out[ec.MEAN_COLUMN] = items.mean(axis=1, skipna=False)
    return out


def long_format(df: pd.DataFrame) -> pd.DataFrame:
    """One row per participant x block x round (rounds without an order are skipped)."""
    records = []
    for _, row in df.iterrows():
        for block in cfg.BLOCKS:
            q_star, opt = game.optimal_order(block)
            table = game.expected_profit_table(block)
            for rnd in range(1, cfg.ROUNDS_PER_BLOCK + 1):
                prefix = game.round_key(block, rnd)
                order = pd.to_numeric(row.get(f"{prefix}_order"), errors="coerce")
                if pd.isna(order):
                    continue
                order = int(order)
                rec = {
                    "participant_id": row["participant_id"],
                    "sequence": row.get("sequence"),
                    "block": block,
                    "supply": cfg.BLOCKS[block]["supply"],
                    "margin": cfg.BLOCKS[block]["margin"],
                    "position": row.get(f"{block}_position"),
                    "round": rnd,
                }
                for field in game.ROUND_FIELDS:
                    rec[field] = row.get(f"{prefix}_{field}")
                rec.update(
                    order=order,
                    q_star=q_star,
                    opt_expected_profit=opt,
                    expected_profit=float(table[order - cfg.ORDER_MIN]),
                    signed_rel_error=(order - q_star) / q_star,
                    abs_rel_error=abs(order - q_star) / q_star,
                )
                rec["profit_share"] = rec["expected_profit"] / opt
                records.append(rec)
    return pd.DataFrame(records)


def block_summary(long: pd.DataFrame) -> pd.DataFrame:
    """One row per participant x block."""
    if long.empty:
        return pd.DataFrame()
    keys = ["participant_id", "sequence", "block", "supply", "margin", "position", "q_star", "opt_expected_profit"]
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


def participant_summary(df: pd.DataFrame, summary: pd.DataFrame) -> pd.DataFrame:
    """Raw rows + EC_mean + per-block errors + supply-uncertainty penalty per margin."""
    out = add_scale_scores(df)
    if summary.empty:
        return out
    measures = ["signed_rel_error", "abs_rel_error", "profit_share", "anchoring_alpha"]
    wide = summary.pivot(index="participant_id", columns="block", values=measures)
    wide.columns = [f"{block}_{measure}" for measure, block in wide.columns]
    for kind in ["abs", "signed"]:
        for margin, (unc, cert) in {"high": ("UH", "CH"), "low": ("UL", "CL")}.items():
            wide[f"penalty_{kind}_error_{margin}"] = (
                wide[f"{unc}_{kind}_rel_error"] - wide[f"{cert}_{kind}_rel_error"]
            )
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
    scored = participant_summary(df, summary)

    for suffix, frame in [("scored", scored), ("long", long), ("block_summary", summary)]:
        path = outdir / f"{stem}_{suffix}.csv"
        frame.to_csv(path, index=False)
        print(f"Wrote {len(frame)} rows to {path}")


if __name__ == "__main__":
    main()
