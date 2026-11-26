"""
All study content and parameters live here: texts, questions, game settings.

Edit this file to adapt the study. You should not need to touch app.py for
content changes.

Question types (for the question pages)
---------------------------------------
  radio     - single choice, vertical (or horizontal=True)
  select    - single choice dropdown, searchable (optional "placeholder")
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
CONTACT_EMAIL = "h12101572@s.wu.ac.at"

# Link handed out to participants (make_participants.py prints BASE_URL?pid=...).
BASE_URL = "https://amt-survey-icssyfjzatvz5h2wih5cfb.streamlit.app"

# Where the 3-page survey block (scales/chen2022.py, pages in SURVEY_PAGES) appears:
#   "after_game"  - after the game, before the control variables (default)
#   "before_game" - after consent, before the game instructions
EC_POSITION = "after_game"

# Optional completion code shown on the thank-you page. Leave empty ("") to hide it.
COMPLETION_CODE = ""

# If Google Sheets is not configured, write to data/responses.csv instead.
# Fine for local testing; set to False for real data collection so a broken
# Sheets config fails loudly instead of silently writing to a local file.
ALLOW_LOCAL_CSV_FALLBACK = False

# Participant IDs starting with this prefix are test runs: never ranked on the admin page.
TEST_ID_PREFIX = "TEST_"

# --------------------------------------------------------------------------- #
# Design: profit margin between subjects (groups H / L),
#         supply within subjects (blocks C / U)
# --------------------------------------------------------------------------- #
GROUPS = {
    "H": {"margin": "high", "unit_cost": 3},
    "L": {"margin": "low", "unit_cost": 9},
}
BLOCKS = {
    "C": {"supply": "certain"},
    "U": {"supply": "uncertain"},
}
ROUNDS_PER_BLOCK = 10

# Block order:
#   "certain_first"   - everyone plays C, then U (default)
#   "counterbalanced" - within each group, half play C -> U and half U -> C
#                       (balanced through assignment.csv; see make_participants.py)
SUPPLY_ORDER = "certain_first"
SUPPLY_ORDERS = {
    "certain_first": ["C", "U"],
    "uncertain_first": ["U", "C"],
}

# File (participant_id, group, supply_order) that takes precedence over the hash
# assignment. Created by make_participants.py. Relative to the app folder.
ASSIGNMENT_FILE = "assignment.csv"
# Shuffle seed of make_participants.py (fixed, so assignment.csv can be regenerated identically).
ASSIGNMENT_SEED = 2026
# Fallback for IDs not in ASSIGNMENT_FILE: group = hash(pid + salt) mod 2.
# Set once before launch and then leave it alone.
ASSIGNMENT_SALT = "660beeb64541"

# --------------------------------------------------------------------------- #
# Game parameters
# --------------------------------------------------------------------------- #
CURRENCY = "coins"  # display label only
PRICE = 12  # selling price p
SALVAGE = 0  # salvage value s of a leftover widget

DEMAND_MIN, DEMAND_MAX = 0, 300  # integer, uniform (mean 150)
ORDER_MIN, ORDER_MAX = 0, 1000  # integer
YIELD_MIN, YIELD_MAX = 0.40, 1.00  # uncertain supply: yield Z uniform (mean 0.70), 2 decimals

# Reference values {group: {block: ...}} (verified by tests/test_game.py against game.optimal_order()).
OPTIMAL_ORDERS = {"H": {"C": 225, "U": 303}, "L": {"C": 75, "U": 101}}
OPTIMAL_EXPECTED_PROFIT = {"H": {"C": 1012.5, "U": 954.1}, "L": {"C": 112.5, "U": 106.0}}

# Pre-drawn demand / yield values (make_sequences.py writes, the app only reads).
SEQUENCES_FILE = "sequences.csv"
SEQUENCE_SEED_START = 2015  # make_sequences.py searches upward from here
DEMAND_MEAN_TOLERANCE = 15  # each block's mean demand within 150 +/- 15
YIELD_MEAN_TOLERANCE = 0.03  # mean yield within 0.70 +/- 0.03
# Extra rules for the pre-drawn demands (the stated range stays DEMAND_MIN-DEMAND_MAX):
DEMAND_DRAW_MIN = 10  # no pre-drawn demand below this (a 0 looks like a bug)
DEMAND_MIN_GAP = 5  # any two pre-drawn demands differ by at least this, so none look repeated

# --------------------------------------------------------------------------- #
# Survey: all 7 constructs of Chen, Wu & Jiang (2022), items in scales/chen2022.py
# --------------------------------------------------------------------------- #
# One list of construct codes per page, in the published order. Page ids are
# survey_p1, survey_p2, ... (also the prefix of their timing columns).
SURVEY_PAGES = [
    ["EC", "EV"],
    ["EAF", "EAT", "ER"],
    ["PSC", "EPB"],
]
# Page (1-based) that shows the attention check, if chen2022.ATTENTION_CHECK is on.
ATTENTION_CHECK_PAGE = 2

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
    "risk11": {
        0: "0 – not at all willing to take risks",
        **{k: str(k) for k in range(1, 10)},
        10: "10 – very willing to take risks",
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

# Worked example in the instructions (uncertain supply), computed with the participant's unit cost.
EXAMPLE = {"order": 150, "usable": 120, "demand": 110}

# {placeholders} are filled per participant by instructions_text(group).
INSTRUCTIONS_TEMPLATE = f"""
You run a small shop that sells widgets. The game has **{N_BLOCKS} blocks of
{ROUNDS_PER_BLOCK} rounds** ({N_ROUNDS} rounds in total).

**Your goal is to earn as much profit as possible. At the end of the session,
the three best players will be announced by participant ID.**

**Each round**
1. You decide how many widgets to order ({ORDER_MIN}–{ORDER_MAX}), **before** you know how many customers will come.
2. Then you see how many widgets were usable and how many customers wanted one (demand).
3. You sell as many widgets as you can: the smaller of your usable widgets and demand.

**Demand.** {DEMAND_RULE} Demand in one round tells you nothing about the next.

**Money**
- You sell each widget for **{PRICE} {CURRENCY}**.
- Your **unit cost is {{unit_cost}} {CURRENCY}** per widget, in every round of the game.
- You pay the unit cost only for **usable** widgets.
- Unsold widgets are scrapped and are worth nothing.
- Profit = {PRICE} × widgets sold − {{unit_cost}} × usable widgets.

**Supply**
- In one block, every widget you order is usable.
- In the other block, only a share between {_yield_lo}% and {_yield_hi}% of the widgets you
  order is usable. Every share in this range is equally likely, on average {_yield_mean}%.

Before each block, a screen tells you that block's supply rule.

**Example** (unit cost {{unit_cost}}, uncertain supply)
- You order {EXAMPLE["order"]} widgets and {EXAMPLE["usable"]} of them are usable. You pay {EXAMPLE["usable"]} × {{unit_cost}} = **{{ex_cost}} {CURRENCY}**.
- Demand is {EXAMPLE["demand"]}, so you sell {EXAMPLE["demand"]} widgets for {EXAMPLE["demand"]} × {PRICE} = **{{ex_revenue}} {CURRENCY}**.
- Your profit is {{ex_revenue}} − {{ex_cost}} = **{{ex_profit}} {CURRENCY}**. The other {{ex_leftover}} usable widgets are scrapped.
"""


def example_outcome(group: str) -> dict:
    """The worked example's numbers for this group's unit cost."""
    c = GROUPS[group]["unit_cost"]
    sales = min(EXAMPLE["demand"], EXAMPLE["usable"])
    revenue, cost = PRICE * sales, c * EXAMPLE["usable"]
    return {"revenue": revenue, "cost": cost, "profit": revenue - cost, "leftover": EXAMPLE["usable"] - sales}


def instructions_text(group: str) -> str:
    ex = example_outcome(group)
    return INSTRUCTIONS_TEMPLATE.format(
        unit_cost=GROUPS[group]["unit_cost"],
        ex_cost=f"{ex['cost']:,}",
        ex_revenue=f"{ex['revenue']:,}",
        ex_profit=f"{ex['profit']:,}",
        ex_leftover=ex["leftover"],
    )


# --------------------------------------------------------------------------- #
# Comprehension check (must be answered correctly to continue)
# --------------------------------------------------------------------------- #
COMPREHENSION_INTRO = (
    "### Quick check\nPlease answer these two questions to make sure the rules are clear. "
    "You can open the instructions above at any time."
)
# Q2 uses the participant's unit cost: {unit_cost} and {cost_total} are filled by comprehension(group).
_Q2 = {"order": 100, "demand": 80}
COMPREHENSION = [
    {
        "id": "comp_q1",
        "label": "You order 200 widgets and 60% of them are usable. How many usable widgets do you receive?",
        "explanation": "60% of 200 widgets are usable: 0.60 × 200 = 120.",
    },
    {
        "id": "comp_q2",
        "label": (
            f"All widgets you order are usable. You order {_Q2['order']} widgets, the unit cost is {{unit_cost}}, "
            f"the price is {PRICE}, and demand is {_Q2['demand']}. What is your profit?"
        ),
        "explanation": (
            f"You pay {_Q2['order']} × {{unit_cost}} = {{cost_total}} for the {_Q2['order']} usable widgets. "
            f"You sell {_Q2['demand']} (demand is {_Q2['demand']}) for {_Q2['demand']} × {PRICE} = "
            f"{PRICE * _Q2['demand']}. Profit = {PRICE * _Q2['demand']} − {{cost_total}}."
        ),
    },
]


def comprehension(group: str) -> list[dict]:
    """COMPREHENSION with this group's unit cost filled in and the correct answers."""
    c = GROUPS[group]["unit_cost"]
    fill = {"unit_cost": c, "cost_total": c * _Q2["order"]}
    answers = {
        "comp_q1": 120,
        "comp_q2": PRICE * min(_Q2["demand"], _Q2["order"]) - c * _Q2["order"],
    }
    return [
        {**q, "label": q["label"].format(**fill), "explanation": q["explanation"].format(**fill),
         "answer": answers[q["id"]]}
        for q in COMPREHENSION
    ]


# --------------------------------------------------------------------------- #
# Control variables
# --------------------------------------------------------------------------- #
# English short names, sorted alphabetically (ignoring accents).
# 193 UN member states, the 2 UN observer states, Kosovo and Taiwan.
COUNTRIES = [
    "Afghanistan", "Albania", "Algeria", "Andorra", "Angola", "Antigua and Barbuda", "Argentina",
    "Armenia", "Australia", "Austria", "Azerbaijan", "Bahamas", "Bahrain", "Bangladesh", "Barbados",
    "Belarus", "Belgium", "Belize", "Benin", "Bhutan", "Bolivia", "Bosnia and Herzegovina", "Botswana",
    "Brazil", "Brunei", "Bulgaria", "Burkina Faso", "Burundi", "Cabo Verde", "Cambodia", "Cameroon",
    "Canada", "Central African Republic", "Chad", "Chile", "China", "Colombia", "Comoros", "Congo",
    "Costa Rica", "Côte d'Ivoire", "Croatia", "Cuba", "Cyprus", "Czechia",
    "Democratic Republic of the Congo", "Denmark", "Djibouti", "Dominica", "Dominican Republic",
    "Ecuador", "Egypt", "El Salvador", "Equatorial Guinea", "Eritrea", "Estonia", "Eswatini",
    "Ethiopia", "Fiji", "Finland", "France", "Gabon", "Gambia", "Georgia", "Germany", "Ghana",
    "Greece", "Grenada", "Guatemala", "Guinea", "Guinea-Bissau", "Guyana", "Haiti", "Holy See",
    "Honduras", "Hungary", "Iceland", "India", "Indonesia", "Iran", "Iraq", "Ireland", "Israel",
    "Italy", "Jamaica", "Japan", "Jordan", "Kazakhstan", "Kenya", "Kiribati", "Kosovo", "Kuwait",
    "Kyrgyzstan", "Laos", "Latvia", "Lebanon", "Lesotho", "Liberia", "Libya", "Liechtenstein",
    "Lithuania", "Luxembourg", "Madagascar", "Malawi", "Malaysia", "Maldives", "Mali", "Malta",
    "Marshall Islands", "Mauritania", "Mauritius", "Mexico", "Micronesia", "Moldova", "Monaco",
    "Mongolia", "Montenegro", "Morocco", "Mozambique", "Myanmar", "Namibia", "Nauru", "Nepal",
    "Netherlands", "New Zealand", "Nicaragua", "Niger", "Nigeria", "North Korea", "North Macedonia",
    "Norway", "Oman", "Pakistan", "Palau", "Palestine", "Panama", "Papua New Guinea", "Paraguay",
    "Peru", "Philippines", "Poland", "Portugal", "Qatar", "Romania", "Russia", "Rwanda",
    "Saint Kitts and Nevis", "Saint Lucia", "Saint Vincent and the Grenadines", "Samoa", "San Marino",
    "Sao Tome and Principe", "Saudi Arabia", "Senegal", "Serbia", "Seychelles", "Sierra Leone",
    "Singapore", "Slovakia", "Slovenia", "Solomon Islands", "Somalia", "South Africa", "South Korea",
    "South Sudan", "Spain", "Sri Lanka", "Sudan", "Suriname", "Sweden", "Switzerland", "Syria",
    "Taiwan", "Tajikistan", "Tanzania", "Thailand", "Timor-Leste", "Togo", "Tonga",
    "Trinidad and Tobago", "Tunisia", "Turkey", "Turkmenistan", "Tuvalu", "Uganda", "Ukraine",
    "United Arab Emirates", "United Kingdom", "United States", "Uruguay", "Uzbekistan", "Vanuatu",
    "Venezuela", "Vietnam", "Yemen", "Zambia", "Zimbabwe",
]

CONTROLS_INTRO = "### About you\nPlease tell us a little about yourself."

CONTROLS = [
    {
        "id": "gender",
        "type": "radio",
        "label": "How do you describe your gender?",
        "options": ["Male", "Female", "Non-binary", "Prefer not to say"],
    },
    {
        "id": "country_upbringing",
        "type": "select",
        "label": (
            "In which country did you spend the largest part of your upbringing "
            "(approximately between the ages of 6 and 18)?"
        ),
        "options": COUNTRIES,
        "placeholder": "Type to search or choose a country…",
    },
    {
        "id": "field_of_study",
        "type": "radio",
        "label": "What is the main field of study of your highest completed post-secondary qualification?",
        "options": [
            "Management",
            "Economics",
            "Technology",
            "Natural Sciences",
            "Social Sciences",
            "Other",
            "No completed post-secondary qualification",
        ],
    },
    {
        "id": "risk_willingness",
        "type": "likert",
        "scale": "risk11",
        "label": "How willing are you to take risks in general?",
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
# Thank you (the score is shown below this text)
# --------------------------------------------------------------------------- #
THANKYOU_TEXT = f"""
### Thank you for taking part!

Your responses have been recorded. You can close this window now.

**What this study is about.** We study how people decide how much to order when
demand is uncertain, and whether that changes when the supply itself is uncertain
(only part of the order is usable). Some participants had a high profit margin
(unit cost 3), others a low one (unit cost 9). All participants saw the same
demand and supply numbers.
[Add any further debriefing.]

If you have any questions, contact {CONTACT_EMAIL}.
"""

SCORE_EXPLANATION = "100 means your orders were the best possible decisions given what you knew."
