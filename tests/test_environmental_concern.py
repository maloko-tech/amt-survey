import math

import pandas as pd

from analysis import add_scale_scores
from scales import environmental_concern as ec

# Verbatim from Chen, Wu & Jiang (2022), Appendix A, Table A1 (revised NEP items, Dunlap et al., 2000).
EXPECTED_TEXTS = [
    "Humans are severely abusing the environment.",
    "If things continue on their present course, we will soon experience a major ecological catastrophe.",
    "The balance of nature is very delicate and easily upset.",
    "Despite our special abilities, humans are still subject to the laws of nature.",
]


def test_item_texts_are_verbatim_and_in_published_order():
    assert [item["text"] for item in ec.ITEMS] == EXPECTED_TEXTS


def test_item_codes():
    assert [item["code"] for item in ec.ITEMS] == ["EC1", "EC2", "EC3", "EC4"]
    assert ec.ITEM_CODES == ["EC1", "EC2", "EC3", "EC4"]


def test_source_citation():
    assert "Chen, L., Wu, Q. and Jiang, L. (2022)" in ec.SOURCE and "10.3390/su14053004" in ec.SOURCE
    assert "Dunlap" in ec.SOURCE and "56(3), 425–442" in ec.SOURCE
    assert "Kamalanon" not in ec.SOURCE


def test_response_format_is_seven_point_with_endpoint_labels_only():
    assert ec.RESPONSE_OPTIONS == [1, 2, 3, 4, 5, 6, 7]
    assert ec.RESPONSE_LABELS == {
        1: "1 – Strongly disagree",
        2: "2",
        3: "3",
        4: "4",
        5: "5",
        6: "6",
        7: "7 – Strongly agree",
    }
    # Only the endpoints carry a text label; the middle options are bare numbers.
    assert [k for k, v in ec.RESPONSE_LABELS.items() if v != str(k)] == [1, 7]


def test_instruction():
    assert ec.INSTRUCTION == "Please rate your level of agreement with the following statements."


def test_questions_render_from_items_without_codes_in_labels():
    qs = ec.questions(attention_check=False)
    assert [q["id"] for q in qs] == ec.ITEM_CODES
    assert [q["label"] for q in qs] == EXPECTED_TEXTS
    assert all(q["options"] == [1, 2, 3, 4, 5, 6, 7] for q in qs)
    assert all(q["labels"] == ec.RESPONSE_LABELS for q in qs)
    assert not any("EC" in q["label"] for q in qs)


def test_attention_check_off_by_default():
    assert ec.ATTENTION_CHECK is False
    assert "ATTN_EC" not in [q["id"] for q in ec.questions()]


def test_attention_check_when_enabled():
    qs = ec.questions(attention_check=True)
    ids = [q["id"] for q in qs]
    assert ids == ["EC1", "EC2", "ATTN_EC", "EC3", "EC4"]
    assert qs[2]["label"] == "For this statement, please select 1 – Strongly disagree."
    assert qs[2]["options"] == [1, 2, 3, 4, 5, 6, 7]
    assert qs[2]["labels"][1] == "1 – Strongly disagree"  # the instructed option exists on the 7-point scale
    assert "ATTN_EC" not in ec.ITEM_CODES  # not part of the scale
    assert ec.attention_passed(1) is True
    assert ec.attention_passed(3) is False
    assert ec.attention_passed(7) is False
    assert ec.attention_passed("") == ""


def test_ec_mean_excludes_attention_check_and_requires_all_items():
    df = pd.DataFrame(
        [
            {"EC1": 1, "EC2": 2, "EC3": 3, "EC4": 4, "ATTN_EC": 5},
            {"EC1": 5, "EC2": None, "EC3": 5, "EC4": 5, "ATTN_EC": 1},
            {"EC1": 7, "EC2": 7, "EC3": 6, "EC4": 6, "ATTN_EC": 7},
        ]
    )
    scored = add_scale_scores(df)
    assert scored.loc[0, "EC_mean"] == 2.5
    assert scored.loc[2, "EC_mean"] == 6.5
    assert math.isnan(scored.loc[1, "EC_mean"])
    assert "EC_mean" not in df.columns  # input not modified


def test_ec_mean_skipped_for_data_without_scale():
    df = pd.DataFrame([{"participant_id": "x", "pre_knowledge": 3}])
    assert "EC_mean" not in add_scale_scores(df).columns
