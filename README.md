# Widget selling game (Streamlit)

A newsvendor experiment with a short survey, based on Käki, Liesiö, Salo & Talluri (2015), *Newsvendor decisions under supply uncertainty*. Each participant plays a "widget selling game": every round they order widgets before knowing demand.

**Flow:** consent → game instructions → comprehension check → game (4 blocks × 5 rounds) → environmental concern scale → demographics → debrief → thank you

- Every question is required unless marked optional. Missing answers are marked in red.
- The participant ID is in the URL (`?pid=P001`). After a reload, the app restores the page, the answers and the game state from the server.
- Each participant gets **one row** in a Google Sheet, with a local CSV as fallback.
- Estimated time per participant: **about 20–25 minutes**.

## Design

2 × 2 **within-subject**: supply (certain / uncertain) × profit margin (high / low). Every participant plays all 4 blocks:

| Block | Supply | Unit cost | Optimal order q\* | E[π(q\*)] |
|---|---|---|---|---|
| CH | certain | 3 (high margin) | 225 | 1012.5 |
| CL | certain | 9 (low margin) | 75 | 112.5 |
| UH | uncertain | 3 | 303 | ≈ 954 |
| UL | uncertain | 9 | 101 | ≈ 106 |

**Game rules:**
- Price 12, salvage value 0.
- Demand is a whole number between 0 and 300, every value equally likely.
- Orders are whole numbers from 0 to 1000.
- With certain supply, every ordered widget is usable.
- With uncertain supply, the usable share Z is uniform between 0.40 and 1.00 (2 decimals), and usable widgets = round_half_up(Z × order).
- Unit cost is paid only for usable widgets.
- Each round: sales = min(demand, usable), profit = 12 × sales − cost × usable.
- All amounts are shown in "coins".

**Counterbalancing:** supply order × margin order, with the same margin order in both halves.

| Sequence | Blocks |
|---|---|
| S1 | CH, CL, UH, UL |
| S2 | CL, CH, UL, UH |
| S3 | UH, UL, CH, CL |
| S4 | UL, UH, CL, CH |

**Same draws for everyone:**
- `sequences.csv` holds pre-drawn demand and yield values. The app only reads this file and never draws numbers while running.
- Draws belong to the block, not the position. Everyone sees the same numbers in UH, whatever their sequence.
- Each block has its own 5 demand values; no demand value appears in more than one block, so participants can't learn a repeating set. Pre-drawn demands are at least `DEMAND_DRAW_MIN` (10) and any two differ by at least `DEMAND_MIN_GAP` (5), so none look like a bug or a near-repeat.
- UH and UL each have their own 5 yield values (none shared). Certain blocks use yield 1.00.
- Each block's mean demand is within 150 ± 15 and each uncertain block's mean yield within 0.70 ± 0.03.

## Project files

| File | What it is |
|---|---|
| `survey_config.py` | **Edit this.** All texts, questions and game parameters. |
| `game.py` | Game logic: round outcome, rounding, expected profit, optimal orders, loading `sequences.csv` / `assignment.csv`. |
| `app.py` | Page flow, required-field checks, game pages, state handling. |
| `storage.py` | Saves the row to Google Sheets (or a local CSV). |
| `scales/environmental_concern.py` | Environmental concern scale (EC1–EC4), quoted verbatim. Don't edit. |
| `make_sequences.py` → `sequences.csv` | Generates the pre-drawn values. Commit the CSV. |
| `make_participants.py` → `assignment.csv` | Creates participant IDs and links. Commit/deploy the CSV. |
| `analysis.py` | Export: long format, per-block summary, per-participant scores. |

## 1. Run locally

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

The app opens at http://localhost:8501. If Google Sheets isn't set up, responses go to `data/responses.csv`.

## 2. Create participant IDs (for class)

```bash
python make_participants.py 40 --base-url https://your-app.streamlit.app
```

This writes `assignment.csv` with P001–P040 and prints one link per participant (`…/?pid=P001`).

- IDs come in shuffled groups of 4, each group containing S1–S4 once. With N a multiple of 4 the sequences are exactly balanced, and they stay balanced if you hand out IDs in order.
- The script won't overwrite an existing `assignment.csv` unless you add `--force`, because IDs may already be handed out.
- `assignment.csv` takes precedence over the fallback assignment. Any ID not in the file (or any visit without an ID) gets `hash(pid + ASSIGNMENT_SALT) mod 4`.
- Set `ASSIGNMENT_SALT` once before launch and don't change it.

## 3. Configure

Everything is in `survey_config.py`:

| Setting | Meaning |
|---|---|
| `ROUNDS_PER_BLOCK` | Rounds per block (default 5). After changing it, re-run `python make_sequences.py`. |
| `PRICE`, `SALVAGE`, `UNIT_COST`, `CURRENCY` | Game economics. `CURRENCY` is a display label only. |
| `DEMAND_MIN/MAX`, `ORDER_MIN/MAX`, `YIELD_MIN/MAX` | Ranges. |
| `SEQUENCES`, `BLOCKS` | Counterbalancing sequences and block definitions. |
| `EC_POSITION` | `"after_game"` (default) or `"before_game"` (right after consent). |
| `BASE_URL` | Default link base for `make_participants.py`. |
| `SEQUENCE_SEED_START`, `*_MEAN_TOLERANCE` | Seed search for `make_sequences.py`. |
| Texts | Consent, instructions, comprehension questions, demographics, debrief, thank you. |

To regenerate the draws, run `python make_sequences.py`. It prints the chosen seed and block means; the current file uses seed 2147, with mean demand 161.6 (CH), 160.0 (CL), 147.8 (UH), 143.2 (UL) and mean yield 0.710 (UH), 0.674 (UL). Regenerate only before data collection starts.

## 4. Connect Google Sheets

1. In the [Google Cloud Console](https://console.cloud.google.com/), enable the **Google Sheets API** and the **Google Drive API**.
2. Create a service account and download a JSON key for it.
3. Share your Google Sheet with the service account's email as **Editor**.
4. Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml` and fill it in.
5. Use a **fresh worksheet** for this design. The default is `widget_game`, created automatically.

A row has about 186 columns. The app widens the sheet grid as needed and appends new columns to the end of the header.

For real data collection, set `ALLOW_LOCAL_CSV_FALLBACK = False`. Never commit `secrets.toml` or the JSON key.

## 5. Deploy (Streamlit Community Cloud)

1. Push the project to GitHub, including `sequences.csv` and `assignment.csv` but without secrets.
2. Create the app on [share.streamlit.io](https://share.streamlit.io) with `app.py` as the entry point.
3. Paste your secrets under **App settings → Secrets**.
4. Under **Advanced settings**, choose the same Python version you use locally, if offered (`requirements.txt` pins the exact package versions).

## Session-day checklist

**Before class (30+ minutes ahead)**
1. In `survey_config.py`, set `ALLOW_LOCAL_CSV_FALLBACK = False` and push. This is the last push before the session.
2. Wake the app: open the live link. Community Cloud apps sleep when unused, and the first load can take a minute.
3. Run one test on the live link with a test ID (e.g. `…/?pid=TEST_LIVE`) and play to the thank-you page. Check that the row appears in the Sheet, then delete that row. The test run also warms the app's Sheet connection.
4. Keep open in your browser:
   - the Google Sheet, to watch rows arrive
   - the app's logs: **Manage app** on the live app. Save retries show up as `[sheets] attempt … failed`.

**During the session**
- **No pushes or redeploys.** A redeploy restarts the app. Participants keep their condition, but mid-game progress restarts from consent.
- If a participant sees "could not be saved", they click **Continue** again. Retries can't create duplicate rows.

**After the session**
- Download the Sheet as CSV and check for duplicate `participant_id`s before running `analysis.py`.

## What participants see

- **Instructions:** plain-language rules plus the worked example. They stay available in an expander during the game.
- **Comprehension check:** both questions must be answered correctly to continue. After a wrong answer the participant sees a short explanation and tries again. Attempts are counted per question.
- **Block intro:** "Block k of 4", the unit cost and the supply rule. A warning box highlights what changed since the previous block.
- **Round:**
  - The page shows the counter, unit cost, price, supply and demand rules, total profit so far, and the earlier rounds of the block.
  - The participant enters an order (required, 0–1000) and confirms it. The round result appears, then a **Next round** button.
  - **A confirmed order is final.** It is stored on the server immediately, so a reload shows that round's result, never a new order form. There is no back navigation.
- **End of game:** total profit, with no leaderboard.

## Data columns (one row per participant)

| Column | Meaning |
|---|---|
| `participant_id`, `sequence`, `supply_order`, `margin_order` | e.g. `P001`, `S3`, `uncertain_first`, `high_first` |
| `started_at`, `submitted_at`, `total_seconds` | Overall timing (UTC, ISO 8601) |
| `comp_q1_attempts`, `comp_q2_attempts` | Attempts until correct |
| `<page>_start`, `<page>_end`, `<page>_seconds` | Pages: consent, instructions, comprehension, game, environmental_concern, demographics, debrief |
| `total_profit` | Sum of all round profits |
| `{CH,CL,UH,UL}_position` | Position 1–4 of the block in this participant's sequence |
| `{block}_r{k}_order`, `_usable`, `_demand`, `_yield`, `_sales`, `_profit` | Per round. Columns are named by block, not position. `_yield` is 1.00 for certain blocks. |
| `{block}_r{k}_seconds` | Time from showing the order form to confirming |
| `consent`, `EC1`–`EC4`, `gender`, `country`, `bachelor_field`, `strategy`, `instructions_clarity`, `feedback` | Answers |

## Environmental concern scale

`scales/environmental_concern.py` is the single source of truth for the 4-item Environmental concern scale (EC1–EC4, no reverse-coded items). It holds the verbatim items, the source citation, the response format and the optional attention check. Don't edit the item texts; a test checks them against the paper.

**Source:** Chen, L., Wu, Q. and Jiang, L. (2022), "Impact of Environmental Concern on Ecological Purchasing Behavior: The Moderating Effect of Prosociality", *Sustainability*, 14(5), 3004, https://doi.org/10.3390/su14053004 (Appendix A, Table A1, "Environmental concern (EC)").

**Original items:** revised NEP scale. Dunlap, R.E., Van Liere, K.D., Mertig, A.G. and Jones, R.E. (2000), "Measuring endorsement of the New Ecological Paradigm: A revised NEP scale", *Journal of Social Issues*, 56(3), 425–442.

- **Response format:** a 7-point Likert scale with only the endpoints labelled, as in the paper. The options are "1 – Strongly disagree", "2", …, "6", "7 – Strongly agree", and the integer **1–7** is stored.
- **Position:** set `EC_POSITION` in `survey_config.py` to `"after_game"` (the default) or `"before_game"`.
- **Attention check:** set `ATTENTION_CHECK = True` in the scale module. It shows "For this statement, please select 1 – Strongly disagree." The answer goes in `ATTN_EC` and the result in `ATTN_EC_passed`. Neither is part of the scale.
- **Stored columns:** `EC1`–`EC4` (integers 1–7) and `environmental_concern_start/_end/_seconds`.
- **Scoring:** `EC_mean` (mean of EC1–EC4) is added only by `analysis.py`.

Data collected with the earlier 5-point scale (Kamalanon et al., 2022, different items) isn't comparable. Keep it out of the same file and worksheet.

## Analysis

```bash
python analysis.py data/responses.csv            # or a CSV downloaded from the Sheet
```

This writes three files next to the input (or to `-o <folder>`):

- **`responses_long.csv`:** one row per participant × block × round, including q\*, E[π(Q)] and the per-round errors.
- **`responses_block_summary.csv`:** one row per participant × block, with:
  - `q_star`, `opt_expected_profit`, `mean_order`
  - `signed_rel_error` (Q − q\*)/q\* and `abs_rel_error` |Q − q\*|/q\*, averaged over rounds
  - `profit_share` = E[π(Q)]/E[π(q\*)], averaged over rounds
  - `anchoring_alpha` = (q\* − mean Q)/(q\* − 150), where 0 = optimal and 1 = anchored at mean demand
- **`responses_scored.csv`:** one row per participant, with:
  - the raw row plus `EC_mean`
  - per-block errors, `profit_share` and `anchoring_alpha` (e.g. `UH_abs_rel_error`)
  - the supply-uncertainty penalties per margin: `penalty_abs_error_high` = abs error(UH) − abs error(CH), `penalty_abs_error_low` = abs error(UL) − abs error(CL), and the same with signed error (`penalty_signed_error_*`)

Expected profit: E[π(q)] = E_Z[p·m(Z·q) − c·Z·q], where m(x) = x − x²/600 for x ≤ 300 and m(x) = 150 otherwise. Z = 1 for certain supply. For uncertain supply, Z is uniform on [0.4, 1] and the expectation is integrated numerically.

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest
```

The tests cover:
- the profit function (worked example 240, comprehension answer 660) and usable-unit rounding
- the optimal orders and expected profits
- that `sequences.csv` is complete, meets the mean criteria and is reproducible
- that `make_participants.py` balances S1–S4
- the analysis measures
- full app flows: a whole game with a saved row, reload after a confirmed order, blank-order rejection, and the `before_game` EC position

The flow tests use a temporary CSV and a temporary assignment file. They never touch Google Sheets or `data/`.

## How state survives reloads

| Event | What happens |
|---|---|
| Browser reload (same URL) | Page, answers, game state and sequence are restored. A played round shows its result. |
| Server restart / redeploy mid-study | The sequence is kept (from `assignment.csv` or the hash); progress restarts from consent. |
| Reload after submitting | Thank-you page; no second row. |

Before analysis, check for duplicate `participant_id`s. They can rarely happen if a save is retried after a network error.
