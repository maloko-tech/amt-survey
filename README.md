# Widget selling game (Streamlit)

A newsvendor experiment with a short survey, based on Käki, Liesiö, Salo & Talluri (2015), *Newsvendor decisions under supply uncertainty*. Each participant plays a "widget selling game": every round they order widgets before knowing demand.

**Flow:** consent → game instructions → comprehension check → game (2 blocks × 10 rounds) → survey (3 pages) → control variables → debrief → thank you (with score)

- Every question is required unless marked optional. Missing answers are marked in red.
- The participant ID is in the URL (`?pid=P001`). After a reload, the app restores the page, the answers and the game state from the server.
- Each participant gets **one row** in a Google Sheet (worksheet `widget_game_v2`), with a local CSV as fallback.
- At the end of the session, the instructor announces the **top 3 by score** from the admin page (`?admin=1`).
- Estimated time per participant: **about 20–25 minutes** (game about 10 min, survey and control questions about 5 min, the rest instructions, comprehension check and debrief).

## Design

**Profit margin between subjects, supply within subjects.**

- **Groups (between subjects):** H (high margin, unit cost 3) and L (low margin, unit cost 9). A participant plays only their group's margin for the whole game.
- **Blocks (within subjects):** every participant plays 2 blocks of `ROUNDS_PER_BLOCK` = 10 rounds: C (certain supply) and U (uncertain supply).
- **Block order:** `SUPPLY_ORDER = "certain_first"` (default) means everyone plays C, then U. With `"counterbalanced"`, half of each group plays C → U and half U → C, balanced through `assignment.csv`.

| Group | Block | Unit cost | Optimal order q\* | E[π(q\*)] |
|---|---|---|---|---|
| H | C | 3 | 225 | 1012.5 |
| H | U | 3 | 303 | ≈ 954 |
| L | C | 9 | 75 | 112.5 |
| L | U | 9 | 101 | ≈ 106 |

**Game rules:**
- Price 12, salvage value 0.
- Demand is a whole number between 0 and 300, every value equally likely.
- Orders are whole numbers from 0 to 1000.
- With certain supply, every ordered widget is usable.
- With uncertain supply, the usable share Z is uniform between 0.40 and 1.00 (2 decimals), and usable widgets = round_half_up(Z × order).
- Unit cost is paid only for usable widgets.
- Each round: sales = min(demand, usable), profit = 12 × sales − cost × usable.
- All amounts are shown in "coins".

**Same draws for everyone, in both groups:**
- `sequences.csv` holds one demand sequence for C, one for U, and one yield sequence for U. The app only reads this file and never draws numbers while running.
- Draws belong to the block, not the position: everyone sees the same numbers in U, whatever their group or block order.
- No demand value appears in more than one block. Pre-drawn demands are at least `DEMAND_DRAW_MIN` (10) and any two differ by at least `DEMAND_MIN_GAP` (5), so none look like a bug or a near-repeat.
- The U yields don't repeat. C uses yield 1.00.
- Each block's mean demand is within 150 ± 15 and the U block's mean yield within 0.70 ± 0.03.

## Score and top-3 announcement

**Score** (stored as `score`, 1 decimal):

score = mean over all 20 rounds of E[π(Q_t)] / E[π(q\*)] × 100

Here q\* and E[π] are for that round's block and the participant's group. The score measures decision quality, not luck: 100 means every order was the best possible decision given what the participant knew. A very large order can make a round's share negative. Ordering 60 in every round of block C gives 96.0 in group L (E[π(60)] = 108 vs 112.5). Over both blocks it gives 89.8, because the optimum in U is 101. The same function (`game.score`) is used by the app and by `analysis.py`.

- **Before the game,** the instructions say: "Your goal is to earn as much profit as possible. At the end of the session, the three best players will be announced by participant ID."
- **On the thank-you page** (after the survey, never earlier), participants see "Your score: X / 100" with one line: "100 means your orders were the best possible decisions given what you knew." They see no ranking.
- **Admin page:** open `https://<app>/?admin=1` and log in with `ADMIN_PASSWORD` from the Streamlit secrets.
  - **Refresh** reads the Sheet once (one API call; there is no auto-refresh).
  - It shows the number of completed participants and the top 3 (participant ID and score, in large font), plus an expandable full ranking.
  - IDs starting with `TEST_` and incomplete rows are left out.
  - Ties are broken by higher `total_profit`, then by earlier `submitted_at`.
  - An admin visit never creates a participant or a row.

## Project files

| File | What it is |
|---|---|
| `survey_config.py` | **Edit this.** All texts, questions, groups, survey pages and game parameters. |
| `game.py` | Game logic: round outcome, rounding, expected profit, optimal orders, score, ranking, loading `sequences.csv` / `assignment.csv`. |
| `app.py` | Page flow, required-field checks, game pages, admin page, state handling. |
| `storage.py` | Saves the row to Google Sheets (or a local CSV) and reads all rows for the admin page. |
| `scales/chen2022.py` | All 7 constructs of Chen et al. (2022), quoted verbatim. Don't edit. |
| `make_sequences.py` → `sequences.csv` | Generates the pre-drawn values. Commit the CSV. |
| `make_participants.py` → `assignment.csv` | Creates participant IDs, groups and links. Commit/deploy the CSV. |
| `analysis.py` | Export: long format, per-block summary, per-participant scores. |

## 1. Run locally

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

The app opens at http://localhost:8501.
- If Google Sheets isn't set up and `ALLOW_LOCAL_CSV_FALLBACK = True`, responses go to `data/responses.csv`.
- A local `.streamlit/secrets.toml` with Sheets credentials writes to the real Sheet, so use a `TEST_` ID when trying things out.

## 2. Create participant IDs (for class)

```bash
python make_participants.py 40 --force
```

This writes `assignment.csv` (`participant_id,group,supply_order`) with P001–P040 and prints one link per participant (`BASE_URL/?pid=P001`).

- **Permuted blocks with a fixed seed** (`ASSIGNMENT_SEED`):
  - With `SUPPLY_ORDER = "certain_first"`, IDs come in blocks of 2: each consecutive pair (P001–P002, P003–P004, …) contains H and L once, in random order.
  - With `"counterbalanced"`, IDs come in blocks of 4 over group × supply order.
  - Either way, the groups stay balanced if you hand out IDs in order.
- The script won't overwrite an existing `assignment.csv` unless you add `--force`, because IDs may already be handed out.
- `assignment.csv` takes precedence. Any ID not in the file gets group `hash(pid + ASSIGNMENT_SALT) mod 2`. With counterbalancing, the next bit of the hash picks the supply order.
- With `SUPPLY_ORDER = "certain_first"`, everyone plays C → U, whatever the file says.
- Set `ASSIGNMENT_SALT` once before launch and don't change it.
- The current `assignment.csv` has 40 IDs (20 H, 20 L, seed 2026). There is no slips script in this project. If you print slips, make them from the new `assignment.csv` (the groups changed).

## 3. Configure

Everything is in `survey_config.py`:

| Setting | Meaning |
|---|---|
| `GROUPS` | H and L with their unit cost (3 and 9). |
| `BLOCKS`, `ROUNDS_PER_BLOCK` | C and U, 10 rounds each. After changing the number of rounds, re-run `python make_sequences.py`. |
| `SUPPLY_ORDER` | `"certain_first"` (default) or `"counterbalanced"`. After changing it, regenerate `assignment.csv`. |
| `PRICE`, `SALVAGE`, `CURRENCY` | Game economics. `CURRENCY` is a display label only. |
| `DEMAND_MIN/MAX`, `ORDER_MIN/MAX`, `YIELD_MIN/MAX` | Ranges. |
| `SURVEY_PAGES`, `ATTENTION_CHECK_PAGE` | Which constructs go on which survey page, and the page with the attention check. |
| `EC_POSITION` | Where the 3 survey pages go: `"after_game"` (default) or `"before_game"` (right after consent). |
| `TEST_ID_PREFIX` | `TEST_`. These IDs are never ranked. |
| `BASE_URL`, `ASSIGNMENT_SEED`, `ASSIGNMENT_SALT` | Links and assignment. |
| `SEQUENCE_SEED_START`, `*_MEAN_TOLERANCE` | Seed search for `make_sequences.py`. |
| Texts | Consent, instructions (`INSTRUCTIONS_TEMPLATE`), comprehension questions, control variables, `COUNTRIES`, debrief, thank you. |

To regenerate the draws, run `python make_sequences.py`. It prints the chosen seed and block means. The current file uses **seed 2019**, with mean demand 155.5 (C) and 151.1 (U), and mean yield 0.676 (U). Regenerate only before data collection starts.

## 4. Connect Google Sheets

1. In the [Google Cloud Console](https://console.cloud.google.com/), enable the **Google Sheets API** and the **Google Drive API**.
2. Create a service account and download a JSON key for it.
3. Share your Google Sheet with the service account's email as **Editor**.
4. Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml` and fill it in, including `ADMIN_PASSWORD`. It must sit above the `[gsheets]` section.
5. Use the worksheet **`widget_game_v2`**, which is created automatically. Old `widget_game` data isn't comparable with this design. A `worksheet = "..."` line in the secrets overrides the default, so set it to `widget_game_v2` there or delete it.

A row has about 220 columns. The app widens the sheet grid as needed and appends new columns to the end of the header.

For real data collection, set `ALLOW_LOCAL_CSV_FALLBACK = False`. Never commit `secrets.toml` or the JSON key.

## 5. Deploy (Streamlit Community Cloud)

1. Push the project to GitHub, including `sequences.csv` and `assignment.csv` but without secrets.
2. Create the app on [share.streamlit.io](https://share.streamlit.io) with `app.py` as the entry point.
3. Paste your secrets under **App settings → Secrets**: `ADMIN_PASSWORD`, `[gsheets]` (with `worksheet = "widget_game_v2"`) and `[gcp_service_account]`.
4. Under **Advanced settings**, choose the same Python version you use locally, if offered (`requirements.txt` pins the exact package versions).

## Session-day checklist

**Before the session (days ahead)**
1. If the class size changed, regenerate the IDs with `python make_participants.py N --force`, commit `assignment.csv`, and reprint the slips from it.
2. In the Streamlit secrets, set `ADMIN_PASSWORD` and `worksheet = "widget_game_v2"`.
3. Check that `ALLOW_LOCAL_CSV_FALLBACK = False` and push. This is the last push before the session. Reboot the app afterwards.

**Before class (30+ minutes ahead)**
1. Wake the app: open the live link. Community Cloud apps sleep when unused, and the first load can take a minute.
2. Run one test on the live link with a test ID (e.g. `…/?pid=TEST_LIVE`) and play to the thank-you page. Check that the row appears in the `widget_game_v2` tab, then delete that row. The test run also warms the app's Sheet connection. `TEST_` rows never appear in the ranking.
3. Open `…/?admin=1`, log in, and click **Refresh** once to check the password and the Sheet access.
4. Keep open in your browser:
   - the Google Sheet, to watch rows arrive
   - the app's logs: **Manage app** on the live app. Save retries show up as `[sheets] attempt … failed`.
   - the admin page (logged in)

**During the session**
- **No pushes or redeploys.** A redeploy restarts the app. Participants keep their group, but mid-game progress restarts from consent.
- If a participant sees "could not be saved", they click **Continue** again. Retries can't create duplicate rows.
- At the end, click **Refresh** on the admin page and announce the top 3 by participant ID.

**After the session**
- Download the Sheet as CSV and check for duplicate `participant_id`s before running `analysis.py`.

## What participants see

- **Instructions:**
  - plain-language rules, with the participant's own unit cost throughout
  - the goal and top-3 sentence
  - a worked example with their unit cost: order 150, 120 usable, demand 110, giving a profit of 960 (H) or 240 (L)

  The instructions stay available in an expander during the game.
- **Comprehension check:** both questions must be answered correctly to continue. Q1 (usable widgets, answer 120) is the same for everyone. Q2 uses the participant's unit cost (answer 660 for H, 60 for L). After a wrong answer the participant sees a short explanation and tries again. Attempts are counted per question.
- **Block intro:** "Block k of 2", the unit cost and the supply rule. Before block 2, a warning box highlights the supply change (and says the unit cost stays the same).
- **Round:**
  - The page shows the counter, unit cost, price, supply and demand rules, total profit so far, and the earlier rounds of the block.
  - The participant enters an order (required, 0–1000) and confirms it. The round result appears, then a **Next round** button.
  - **A confirmed order is final.** It is stored on the server immediately, so a reload shows that round's result, never a new order form. There is no back navigation.
- **End of game:** total profit only (no score yet).
- **Survey:** 3 pages (see below).
- **Control variables:** 4 required questions.
- **Thank you:** debriefing text and "Your score: X / 100".

## Survey: Chen et al. (2022), 7 constructs

`scales/chen2022.py` is the single source of truth for all 32 items. It holds the items, codes, construct names, source, response format and attention check. Don't edit the item texts; a test checks every one of them against the paper. Wording, punctuation and order are unchanged; EAF2 uses a typographic apostrophe (’).

**Source:** Chen, L., Wu, Q. and Jiang, L. (2022), "Impact of Environmental Concern on Ecological Purchasing Behavior: The Moderating Effect of Prosociality", *Sustainability*, 14(5), 3004, https://doi.org/10.3390/su14053004, Appendix A, Table A1.

The EC items come from the revised NEP scale: Dunlap, R.E., Van Liere, K.D., Mertig, A.G. and Jones, R.E. (2000), "Measuring endorsement of the New Ecological Paradigm: A revised NEP scale", *Journal of Social Issues*, 56(3), 425–442.

| Page | Constructs (items) |
|---|---|
| `survey_p1` | Environmental concern EC1–EC4, Ecological values EV1–EV6 |
| `survey_p2` | Ecological affects EAF1–EAF5, Ecological attitudes EAT1–EAT3, **attention check**, Ecological responsibility ER1–ER4 |
| `survey_p3` | Prosociality PSC1–PSC5, Ecological purchasing behavior EPB1–EPB5 |

- **Response format:** 7-point Likert for all items: "1 – Strongly disagree", "2", …, "6", "7 – Strongly agree". The integer 1–7 is stored. There are no reverse-coded items.
- **UI:** same instruction on each page ("Please rate your level of agreement with the following statements."), horizontal radios with nothing preselected, all required, no codes or construct names shown, no going back.
- **Attention check:** on page 2, after EAT1 (`ATTENTION_CHECK = True` in the scale module). It reads "For this statement, please select 1 – Strongly disagree." The answer goes in `ATTN` and the result in `ATTN_passed`. Neither is part of a construct.
- **Position:** `EC_POSITION` moves the whole 3-page block: `"after_game"` (default) or `"before_game"`.
- **Scoring:** `EC_mean`, `EV_mean`, `EAF_mean`, `EAT_mean`, `ER_mean`, `PSC_mean` and `EPB_mean` are added only by `analysis.py`.

## Control variables (all required)

| Column | Question | Answer |
|---|---|---|
| `gender` | How do you describe your gender? | Male / Female / Non-binary / Prefer not to say |
| `country_upbringing` | In which country did you spend the largest part of your upbringing (approximately between the ages of 6 and 18)? | Searchable dropdown of 197 countries (`COUNTRIES` in `survey_config.py`: 193 UN members, the 2 observer states, Kosovo and Taiwan), nothing preselected |
| `field_of_study` | What is the main field of study of your highest completed post-secondary qualification? | Management / Economics / Technology / Natural Sciences / Social Sciences / Other / No completed post-secondary qualification |
| `risk_willingness` | How willing are you to take risks in general? | Horizontal 0–10, only the endpoints labelled ("0 – not at all willing to take risks", "10 – very willing to take risks"). The integer is stored. |

## Data columns (one row per participant)

| Column | Meaning |
|---|---|
| `participant_id`, `group`, `unit_cost`, `supply_order` | e.g. `P001`, `L`, `9`, `certain_first` |
| `started_at`, `submitted_at`, `total_seconds` | Overall timing (UTC, ISO 8601) |
| `comp_q1_attempts`, `comp_q2_attempts` | Attempts until correct |
| `<page>_start`, `<page>_end`, `<page>_seconds` | Pages: consent, instructions, comprehension, game, survey_p1, survey_p2, survey_p3, controls, debrief |
| `total_profit` | Sum of all round profits |
| `score` | See [Score](#score-and-top-3-announcement) |
| `C_position`, `U_position` | Position 1–2 of the block |
| `{C,U}_r{k}_order`, `_usable`, `_demand`, `_yield`, `_sales`, `_profit` | Per round (k = 1–10). `_yield` is 1.00 in C. |
| `{C,U}_r{k}_seconds` | Time from showing the order form to confirming |
| `consent` | Consent answer |
| `EC1`–`EC4`, `EV1`–`EV6`, `EAF1`–`EAF5`, `EAT1`–`EAT3`, `ER1`–`ER4`, `PSC1`–`PSC5`, `EPB1`–`EPB5` | Survey answers (1–7) |
| `ATTN`, `ATTN_passed` | Attention check |
| `gender`, `country_upbringing`, `field_of_study`, `risk_willingness` | Control variables |
| `strategy`, `instructions_clarity`, `feedback` | Debrief |

## Analysis

```bash
python analysis.py data/responses.csv            # or a CSV downloaded from the Sheet
```

This writes three files next to the input (or to `-o <folder>`):

- **`responses_long.csv`:** one row per participant × block (C, U) × round, including q\*, E[π(Q)], `profit_share` and the per-round errors.
- **`responses_block_summary.csv`:** one row per participant × block, with:
  - `q_star`, `opt_expected_profit`, `mean_order` (q\* for the participant's group)
  - `signed_rel_error` (Q − q\*)/q\* and `abs_rel_error` |Q − q\*|/q\*, averaged over rounds
  - `profit_share` = E[π(Q)]/E[π(q\*)], averaged over rounds
  - `anchoring_alpha` = (q\* − mean Q)/(q\* − 150), where 0 = optimal and 1 = anchored at mean demand
- **`responses_scored.csv`:** one row per participant, with:
  - the raw row plus `group` and `score` (recomputed with `game.score`; equals the stored column)
  - per-block measures (e.g. `U_abs_rel_error`, `C_profit_share`)
  - `penalty_abs_error` = abs error(U) − abs error(C), `penalty_signed_error` = signed error(U) − signed error(C), `penalty_profit_share` = profit share(C) − profit share(U)
  - the construct means `EC_mean`, `EV_mean`, `EAF_mean`, `EAT_mean`, `ER_mean`, `PSC_mean`, `EPB_mean` (empty if an item is missing)

Expected profit: E[π(q)] = E_Z[p·m(Z·q) − c·Z·q], where m(x) = x − x²/600 for x ≤ 300 and m(x) = 150 otherwise. Z = 1 for certain supply. For uncertain supply, Z is uniform on [0.4, 1] and the expectation is integrated numerically.

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest
```

The tests cover:
- the profit function: worked example and comprehension Q2 per group (960/240, 660/60), and usable-unit rounding
- the optimal orders and expected profits for both groups and blocks
- the score: L ordering 60 in C gives 96.0, alternating 75 and 45 gives 92.0, optimal orders give 100
- the ranking: `TEST_` rows and incomplete rows excluded, tie-breaks applied
- that `sequences.csv` is complete, meets the mean and spacing criteria and is reproducible
- group assignment: blocks of 2, blocks of 4 when counterbalanced, the fixed seed, the hash fallback, and that `assignment.csv` matches the generator
- the survey: all 32 items verbatim and in order, construct names, the 7-point options, the page layout and the attention check
- the control questions and their options
- the analysis measures and construct means
- full app flows for one H and one L participant, each with a saved row and the score on the thank-you page; also counterbalanced U → C, reload after a confirmed order, blank-order rejection, and the `before_game` survey position
- the admin page: it needs the password, stays locked without `ADMIN_PASSWORD`, and its top 3 leaves out `TEST_` and incomplete rows
- Sheets saving: API calls, retries, no duplicates, and the single read for the admin page

The flow tests use a temporary CSV and a temporary assignment file. They never touch Google Sheets or `data/`.

## How state survives reloads

| Event | What happens |
|---|---|
| Browser reload (same URL) | Page, answers, game state and group are restored. A played round shows its result. |
| Server restart / redeploy mid-study | The group and block order are kept (from `assignment.csv` or the hash); progress restarts from consent. |
| Reload after submitting | Thank-you page with the score; no second row. |

Before analysis, check for duplicate `participant_id`s. They can rarely happen if a save is retried after a network error.
