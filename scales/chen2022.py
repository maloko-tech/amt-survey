"""
Survey scales of Chen, Wu & Jiang (2022): all 7 constructs. This module is the
single source of truth for the items, codes, construct names, source, response
format and attention check. The survey pages, the stored columns and the
scoring in analysis.py are all derived from it.

Do not edit the item texts: they are quoted verbatim (wording, punctuation and
order) from Appendix A, Table A1 of the source below. EAF2 uses a typographic
apostrophe (’).
"""

SOURCE = (
    "Chen, L., Wu, Q. and Jiang, L. (2022), \"Impact of Environmental Concern on Ecological "
    "Purchasing Behavior: The Moderating Effect of Prosociality\", Sustainability, 14(5), 3004, "
    "https://doi.org/10.3390/su14053004 (Appendix A, Table A1)."
)
# The EC items come from the revised NEP scale.
EC_ORIGIN = (
    "Revised NEP scale: Dunlap, R.E., Van Liere, K.D., Mertig, A.G. and Jones, R.E. (2000), "
    "\"Measuring endorsement of the New Ecological Paradigm: A revised NEP scale\", "
    "Journal of Social Issues, 56(3), 425–442."
)

INSTRUCTION = "Please rate your level of agreement with the following statements."

# Published order. No reverse-coded items.
CONSTRUCTS = [
    {
        "code": "EC",
        "name": "Environmental concern",
        "items": [
            "Humans are severely abusing the environment.",
            "If things continue on their present course, we will soon experience a major ecological catastrophe.",
            "The balance of nature is very delicate and easily upset.",
            "Despite our special abilities, humans are still subject to the laws of nature.",
        ],
    },
    {
        "code": "EV",
        "name": "Ecological values",
        "items": [
            "It makes me sad to see natural environments destroyed.",
            "Nature is valuable for its own sake.",
            "One of the most important reasons to conserve is to preserve wild areas.",
            "Nature is important because of what it can contribute to the pleasure and welfare of humans.",
            "We need to preserve resources to maintain a high quality of life.",
            "One of the most important reasons to conserve is to ensure a continued high standard of living.",
        ],
    },
    {
        "code": "EAF",
        "name": "Ecological affects",
        "items": [
            "It frightens me to think that much of the food I eat is contaminated with pesticides.",
            "It genuinely infuriates me to think that the government doesn’t do more to help control "
            "pollution of the environment.",
            "I become incensed when I think about the harm being done to plant and animal life by pollution.",
            "I get depressed on smoggy days.",
            "When I think of the ways industries are polluting, I get frustrated and angry.",
        ],
    },
    {
        "code": "EAT",
        "name": "Ecological attitudes",
        "items": [
            "I like the idea of purchasing ecologically.",
            "Purchasing ecologically is a good idea.",
            "I have a favorable attitude toward purchasing an ecological version of a product.",
        ],
    },
    {
        "code": "ER",
        "name": "Ecological responsibility",
        "items": [
            "My actions impact the health of the environment.",
            "I have the power to protect the environment.",
            "I can learn how to improve the environment.",
            "I will work to make my surrounding environment a better place.",
        ],
    },
    {
        "code": "PSC",
        "name": "Prosociality",
        "items": [
            "It is important that others are happy.",
            "It is important to help someone who needs it.",
            "I want to help others.",
            "The well-being of others is important.",
            "It is important that all people are happy.",
        ],
    },
    {
        "code": "EPB",
        "name": "Ecological purchasing behavior",
        "items": [
            "I make a special effort to buy paper and plastic products that are made from recycled materials.",
            "I have switched products for ecological reasons.",
            "When I have a choice between two equal products, I purchase the one less harmful to other "
            "people and the environment.",
            "I make a special effort to buy household chemicals, such as detergents and cleaning solutions, "
            "that are environmentally friendly.",
            "I have avoided buying a product because it had potentially harmful environmental effects.",
        ],
    },
]
CONSTRUCT_CODES = [c["code"] for c in CONSTRUCTS]
BY_CODE = {c["code"]: c for c in CONSTRUCTS}

# Flat list of items: {"code": "EV3", "construct": "EV", "text": ...}
ITEMS = [
    {"code": f"{c['code']}{i}", "construct": c["code"], "text": text}
    for c in CONSTRUCTS
    for i, text in enumerate(c["items"], start=1)
]
ITEM_CODES = [item["code"] for item in ITEMS]


def item_codes(construct: str) -> list[str]:
    return [item["code"] for item in ITEMS if item["construct"] == construct]


# Columns added at the export/analysis step only (never shown to participants).
MEAN_COLUMNS = {code: f"{code}_mean" for code in CONSTRUCT_CODES}

# Seven-point Likert scale with only the endpoints labelled, as in the paper.
# The integer is what gets stored.
RESPONSE_OPTIONS = [1, 2, 3, 4, 5, 6, 7]
RESPONSE_LABELS = {
    1: "1 – Strongly disagree",
    2: "2",
    3: "3",
    4: "4",
    5: "5",
    6: "6",
    7: "7 – Strongly agree",
}

# Instructed-response item. It is NOT part of any construct: it is stored in its
# own column (ATTN) plus a pass/fail column (ATTN_passed) and never enters a mean.
# The page it appears on is survey_config.ATTENTION_CHECK_PAGE.
ATTENTION_CHECK = True
ATTENTION_ITEM = {
    "code": "ATTN",
    "text": "For this statement, please select 1 – Strongly disagree.",
    "correct": 1,
}
# Shown after this many items of its page (the scale items keep their order).
ATTENTION_AFTER_ITEM = 6


def _question(code: str, text: str) -> dict:
    return {
        "id": code,
        "type": "likert",
        "label": text,
        "options": RESPONSE_OPTIONS,
        "labels": RESPONSE_LABELS,
    }


def questions(constructs: list[str], attention_check: bool = False) -> list[dict]:
    """The items of these constructs (in published order) in the format app.py renders."""
    qs = [_question(item["code"], item["text"]) for code in constructs for item in ITEMS if item["construct"] == code]
    if attention_check:
        qs.insert(min(ATTENTION_AFTER_ITEM, len(qs)), _question(ATTENTION_ITEM["code"], ATTENTION_ITEM["text"]))
    return qs


def attention_passed(answer) -> bool | str:
    """Pass/fail for the attention check ('' if it wasn't answered)."""
    if answer is None or answer == "":
        return ""
    return int(answer) == ATTENTION_ITEM["correct"]
