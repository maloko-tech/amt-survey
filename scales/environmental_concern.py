"""
Environmental concern (EC) scale. This module is the single source of truth for
its items, response format and attention check. The survey page, the stored
columns and the scoring in analysis.py are all derived from it.

Do not edit the item texts: they are quoted verbatim from the source below.
"""

SOURCE = (
    "Chen, L., Wu, Q. and Jiang, L. (2022), \"Impact of Environmental Concern on Ecological "
    "Purchasing Behavior: The Moderating Effect of Prosociality\", Sustainability, 14(5), 3004, "
    "https://doi.org/10.3390/su14053004 (Appendix A, Table A1, \"Environmental concern (EC)\"). "
    "Original items: revised NEP scale, Dunlap, R.E., Van Liere, K.D., Mertig, A.G. and Jones, R.E. "
    "(2000), \"Measuring endorsement of the New Ecological Paradigm: A revised NEP scale\", "
    "Journal of Social Issues, 56(3), 425–442."
)
CONSTRUCT = "Environmental concern (EC)"

# Page id; also the prefix of the block's timestamp columns
# (environmental_concern_start / _end / _seconds).
PAGE_ID = "environmental_concern"

INSTRUCTION = "Please rate your level of agreement with the following statements."

# Published order. No reverse-coded items.
ITEMS = [
    {"code": "EC1", "text": "Humans are severely abusing the environment."},
    {"code": "EC2", "text": "If things continue on their present course, we will soon experience a major ecological catastrophe."},
    {"code": "EC3", "text": "The balance of nature is very delicate and easily upset."},
    {"code": "EC4", "text": "Despite our special abilities, humans are still subject to the laws of nature."},
]
ITEM_CODES = [item["code"] for item in ITEMS]

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

# Optional instructed-response item. It is NOT part of the scale: it is stored
# in its own column (ATTN_EC) plus a pass/fail column (ATTN_EC_passed) and is
# never included in EC_mean.
ATTENTION_CHECK = False
ATTENTION_ITEM = {
    "code": "ATTN_EC",
    "text": "For this statement, please select 1 – Strongly disagree.",
    "correct": 1,
}
# When enabled, the check is shown after this many scale items (EC1-EC4 keep their order).
ATTENTION_AFTER_ITEM = 2

# Column added at the export/analysis step only (never shown to participants).
MEAN_COLUMN = "EC_mean"


def _question(code: str, text: str) -> dict:
    return {
        "id": code,
        "type": "likert",
        "label": text,
        "options": RESPONSE_OPTIONS,
        "labels": RESPONSE_LABELS,
    }


def questions(attention_check: bool | None = None) -> list[dict]:
    """The block's questions in the format app.py renders."""
    if attention_check is None:
        attention_check = ATTENTION_CHECK
    qs = [_question(item["code"], item["text"]) for item in ITEMS]
    if attention_check:
        qs.insert(ATTENTION_AFTER_ITEM, _question(ATTENTION_ITEM["code"], ATTENTION_ITEM["text"]))
    return qs


def attention_passed(answer) -> bool | str:
    """Pass/fail for the attention check ('' if it wasn't answered)."""
    if answer is None or answer == "":
        return ""
    return int(answer) == ATTENTION_ITEM["correct"]
