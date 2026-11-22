"""
All study content and parameters live here: texts, questions, game settings.

Edit this file to adapt the study. You should not need to touch app.py for
content changes.

Question types (for the question pages)
---------------------------------------
  radio     - single choice, vertical (or horizontal=True)
  select    - single choice dropdown
  likert    - single choice on a numeric scale (see SCALES); stores the number
  multi     - multiple choice; stores options joined with "; "
  text      - short free text
  textarea  - long free text
  number    - numeric input (min / max / step optional)

Every question is required unless it has "required": False.
Question "id"s become column names in the Google Sheet, so keep them unique,
short, and stable once data collection has started.
"""

# --------------------------------------------------------------------------- #
# General settings
# --------------------------------------------------------------------------- #
STUDY_TITLE = "Widget selling game"
INSTITUTION = "WU Vienna"
CONTACT_EMAIL = "[researcher@university.edu]"  # TODO: replace

# Link handed out to participants (make_participants.py prints BASE_URL?pid=...).
BASE_URL = "http://localhost:8501"  # TODO: replace with the deployed app URL

# Where the Environmental concern block (scales/environmental_concern.py) appears:
#   "after_game"  - after the game, before demographics (default)
#   "before_game" - after consent, before the game instructions
EC_POSITION = "after_game"

# Optional completion code shown on the thank-you page. Leave empty ("") to hide it.
COMPLETION_CODE = ""

# If Google Sheets is not configured, write to data/responses.csv instead.
# Fine for local testing; set to False for real data collection so a broken
# Sheets config fails loudly instead of silently writing to a local file.
ALLOW_LOCAL_CSV_FALLBACK = True

# --------------------------------------------------------------------------- #
# Design: 2 x 2 within-subject (supply x profit margin), 4 blocks
# --------------------------------------------------------------------------- #
BLOCKS = {
    "CH": {"supply": "certain", "margin": "high"},
    "CL": {"supply": "certain", "margin": "low"},
    "UH": {"supply": "uncertain", "margin": "high"},
    "UL": {"supply": "uncertain", "margin": "low"},
}
ROUNDS_PER_BLOCK = 5

# Counterbalancing: supply order x margin order (same margin order in both supply halves).
SEQUENCES = {
    "S1": ["CH", "CL", "UH", "UL"],
    "S2": ["CL", "CH", "UL", "UH"],
    "S3": ["UH", "UL", "CH", "CL"],
    "S4": ["UL", "UH", "CL", "CH"],
}

# Optional file (participant_id, sequence) that takes precedence over the hash
# assignment. Created by make_participants.py. Relative to the app folder.
ASSIGNMENT_FILE = "assignment.csv"
# Fallback for IDs not in ASSIGNMENT_FILE: sequence = hash(pid + salt) mod 4.
# Set once before launch and then leave it alone.
ASSIGNMENT_SALT = "change-me-before-launch"

# --------------------------------------------------------------------------- #
# Game parameters
# --------------------------------------------------------------------------- #
CURRENCY = "coins"  # display label only
PRICE = 12  # selling price p
SALVAGE = 0  # salvage value s of a leftover widget
UNIT_COST = {"high": 3, "low": 9}  # unit cost c by profit margin; paid only for usable units

DEMAND_MIN, DEMAND_MAX = 0, 300  # integer, uniform (mean 150)
ORDER_MIN, ORDER_MAX = 0, 1000  # integer
YIELD_MIN, YIELD_MAX = 0.40, 1.00  # uncertain supply: yield Z uniform (mean 0.70), 2 decimals

# Reference values (verified by tests/test_game.py against game.optimal_order()).
OPTIMAL_ORDERS = {"CH": 225, "CL": 75, "UH": 303, "UL": 101}
OPTIMAL_EXPECTED_PROFIT = {"CH": 1012.5, "CL": 112.5, "UH": 954.1, "UL": 106.0}

# Pre-drawn demand / yield values (make_sequences.py writes, the app only reads).
SEQUENCES_FILE = "sequences.csv"
SEQUENCE_SEED_START = 2015  # make_sequences.py searches upward from here
DEMAND_MEAN_TOLERANCE = 15  # each block's mean demand within 150 +/- 15
YIELD_MEAN_TOLERANCE = 0.03  # mean yield within 0.70 +/- 0.03

# --------------------------------------------------------------------------- #
# Answer scales
# --------------------------------------------------------------------------- #
SCALES = {
    "clarity5": {
        1: "1 – Very unclear",
        2: "2",
        3: "3",
        4: "4",
        5: "5 – Very clear",
    },
}

# --------------------------------------------------------------------------- #
# Consent
# --------------------------------------------------------------------------- #
N_BLOCKS = len(BLOCKS)
N_ROUNDS = N_BLOCKS * ROUNDS_PER_BLOCK

CONSENT_TEXT = f"""
### Informed consent

You are invited to take part in a research study on ordering decisions,
conducted at {INSTITUTION}.

**What you will do.** You will play a short game in which you decide how many
widgets to order for a shop ({N_ROUNDS} rounds), and then answer a few questions
about yourself and the game. This takes about **20–25 minutes**.

**Voluntary participation.** Taking part is voluntary. You may stop at any time
by closing this window, without giving a reason and without any disadvantage.

**Data.** Your answers are stored under your participant ID only and are used
for research purposes only.
"""

CONSENT_QUESTIONS = [
    {
        "id": "consent",
        "type": "radio",
        "label": "Do you agree to take part in this study?",
        "options": [
            "I have read the information above and agree to take part.",
            "I do not agree to take part.",
        ],
    },
]
# The option that counts as consent (anything else ends the survey).
CONSENT_YES = CONSENT_QUESTIONS[0]["options"][0]

DECLINED_TEXT = """
### Thank you

You chose not to take part. No data has been stored. You can close this window now.
"""

# --------------------------------------------------------------------------- #
# Game instructions (also shown in an expander during the game)
# --------------------------------------------------------------------------- #
_yield_lo, _yield_hi = round(YIELD_MIN * 100), round(YIELD_MAX * 100)
_yield_mean = round((YIELD_MIN + YIELD_MAX) / 2 * 100)
_demand_mean = (DEMAND_MIN + DEMAND_MAX) // 2

SUPPLY_RULE = {
    "certain": "Every widget you order is usable.",
    "uncertain": (
        f"Only a share between {_yield_lo}% and {_yield_hi}% of the widgets you order is usable "
        f"(every share equally likely, on average {_yield_mean}%)."
    ),
}
DEMAND_RULE = (
    f"Demand is between {DEMAND_MIN} and {DEMAND_MAX}, on average {_demand_mean}. "
    "Every value in this range is equally likely."
)

INSTRUCTIONS_TEXT = f"""
You run a small shop that sells widgets. The game has **{N_BLOCKS} blocks of
{ROUNDS_PER_BLOCK} rounds** ({N_ROUNDS} rounds in total). Your goal is to earn
as much profit as possible over all rounds.

**Each round**
1. You decide how many widgets to order ({ORDER_MIN}–{ORDER_MAX}), **before** you know how many customers will come.
2. Then you see how many widgets were usable and how many customers wanted one (demand).
3. You sell as many widgets as you can: the smaller of your usable widgets and demand.

**Demand.** {DEMAND_RULE} Demand in one round tells you nothing about the next.

**Money**
- You sell each widget for **{PRICE} {CURRENCY}**.
- You pay the **unit cost** only for **usable** widgets.
- The unit cost changes between blocks.
- Unsold widgets are scrapped and are worth nothing.
- Profit = {PRICE} × widgets sold − unit cost × usable widgets.

**Supply**
- In some blocks, every widget you order is usable.
- In other blocks, only a share between {_yield_lo}% and {_yield_hi}% of the widgets you
  order is usable. Every share in this range is equally likely, on average {_yield_mean}%.

Before each block, a screen tells you that block's unit cost and supply rule.

**Example** (unit cost 9, uncertain supply)
- You order 150 widgets and 120 of them are usable. You pay 120 × 9 = **1,080 {CURRENCY}**.
- Demand is 110, so you sell 110 widgets for 110 × 12 = **1,320 {CURRENCY}**.
- Your profit is 1,320 − 1,080 = **240 {CURRENCY}**. The other 10 usable widgets are scrapped.
"""

# --------------------------------------------------------------------------- #
# Comprehension check (must be answered correctly to continue)
# --------------------------------------------------------------------------- #
COMPREHENSION_INTRO = (
    "### Quick check\nPlease answer these two questions to make sure the rules are clear. "
    "You can open the instructions above at any time."
)
COMPREHENSION = [
    {
        "id": "comp_q1",
        "label": "You order 200 widgets and 60% of them are usable. How many usable widgets do you receive?",
        "answer": 120,
        "explanation": "60% of 200 widgets are usable: 0.60 × 200 = 120.",
    },
    {
        "id": "comp_q2",
        "label": (
            "All widgets you order are usable. You order 100 widgets, the unit cost is 3, "
            "the price is 12, and demand is 80. What is your profit?"
        ),
        "answer": 660,
        "explanation": (
            "You pay 100 × 3 = 300 for the 100 usable widgets. You sell 80 (demand is 80) "
            "for 80 × 12 = 960. Profit = 960 − 300."
        ),
    },
]

# --------------------------------------------------------------------------- #
# Demographics
# --------------------------------------------------------------------------- #
DEMOGRAPHICS_INTRO = "### About you\nPlease tell us a little about yourself."

DEMOGRAPHICS = [
    {
        "id": "gender",
        "type": "radio",
        "label": "What is your gender?",
        "options": ["Female", "Male", "Non-binary / other", "Prefer not to say"],
    },
    {
        "id": "country",
        "type": "text",
        "label": "In which country or region did you grow up?",
    },
    {
        "id": "bachelor_field",
        "type": "radio",
        "label": "In which field is your bachelor's degree?",
        "options": ["Business", "Economics", "Engineering", "Other"],
    },
]

# --------------------------------------------------------------------------- #
# Debrief questions
# --------------------------------------------------------------------------- #
DEBRIEF_INTRO = "### About the game\nAlmost done. Please tell us about your experience."

DEBRIEF = [
    {
        "id": "strategy",
        "type": "textarea",
        "label": "Please describe how you decided on your order quantities.",
    },
    {
        "id": "instructions_clarity",
        "type": "likert",
        "scale": "clarity5",
        "label": "How clear were the instructions?",
    },
    {
        "id": "feedback",
        "type": "textarea",
        "label": "Any other feedback?",
        "required": False,
    },
]

# --------------------------------------------------------------------------- #
# Thank you
# --------------------------------------------------------------------------- #
THANKYOU_TEXT = f"""
### Thank you for taking part!

Your responses have been recorded. You can close this window now.

**What this study is about.** We study how people decide how much to order when
demand is uncertain, and whether that changes when the supply itself is uncertain
(only part of the order is usable) and when profit margins are high or low.
All participants saw the same demand and supply numbers, in different block orders.
[Add any further debriefing.]

If you have any questions, contact {CONTACT_EMAIL}.
"""
