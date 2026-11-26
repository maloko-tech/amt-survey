import math

import pandas as pd

import survey_config as cfg
from analysis import add_scale_scores
from scales import chen2022 as scale

# Verbatim from Chen, Wu & Jiang (2022), Appendix A, Table A1 (EC: revised NEP items, Dunlap et al., 2000).
# Typed independently of scales/chen2022.py on purpose: this is the check against the paper.
EXPECTED = {
    "EC1": "Humans are severely abusing the environment.",
    "EC2": "If things continue on their present course, we will soon experience a major ecological catastrophe.",
    "EC3": "The balance of nature is very delicate and easily upset.",
    "EC4": "Despite our special abilities, humans are still subject to the laws of nature.",
    "EV1": "It makes me sad to see natural environments destroyed.",
    "EV2": "Nature is valuable for its own sake.",
    "EV3": "One of the most important reasons to conserve is to preserve wild areas.",
    "EV4": "Nature is important because of what it can contribute to the pleasure and welfare of humans.",
    "EV5": "We need to preserve resources to maintain a high quality of life.",
    "EV6": "One of the most important reasons to conserve is to ensure a continued high standard of living.",
    "EAF1": "It frightens me to think that much of the food I eat is contaminated with pesticides.",
    "EAF2": "It genuinely infuriates me to think that the government doesn’t do more to help control pollution of the environment.",
    "EAF3": "I become incensed when I think about the harm being done to plant and animal life by pollution.",
    "EAF4": "I get depressed on smoggy days.",
    "EAF5": "When I think of the ways industries are polluting, I get frustrated and angry.",
    "EAT1": "I like the idea of purchasing ecologically.",
    "EAT2": "Purchasing ecologically is a good idea.",
    "EAT3": "I have a favorable attitude toward purchasing an ecological version of a product.",
    "ER1": "My actions impact the health of the environment.",
    "ER2": "I have the power to protect the environment.",
    "ER3": "I can learn how to improve the environment.",
    "ER4": "I will work to make my surrounding environment a better place.",
    "PSC1": "It is important that others are happy.",
    "PSC2": "It is important to help someone who needs it.",
    "PSC3": "I want to help others.",
    "PSC4": "The well-being of others is important.",
    "PSC5": "It is important that all people are happy.",
    "EPB1": "I make a special effort to buy paper and plastic products that are made from recycled materials.",
    "EPB2": "I have switched products for ecological reasons.",
    "EPB3": "When I have a choice between two equal products, I purchase the one less harmful to other people and the environment.",
    "EPB4": "I make a special effort to buy household chemicals, such as detergents and cleaning solutions, that are environmentally friendly.",
    "EPB5": "I have avoided buying a product because it had potentially harmful environmental effects.",
}
CONSTRUCTS = {
    "EC": "Environmental concern",
    "EV": "Ecological values",
    "EAF": "Ecological affects",
    "EAT": "Ecological attitudes",
    "ER": "Ecological responsibility",
    "PSC": "Prosociality",
    "EPB": "Ecological purchasing behavior",
}


def test_all_32_items_verbatim_and_in_published_order():
    assert len(scale.ITEMS) == 32
    assert {item["code"]: item["text"] for item in scale.ITEMS} == EXPECTED
    assert scale.ITEM_CODES == list(EXPECTED)  # order


def test_eaf2_typographic_apostrophe():
    text = next(i["text"] for i in scale.ITEMS if i["code"] == "EAF2")
    assert "doesn’t" in text and "'" not in text


def test_constructs_codes_and_names():
    assert scale.CONSTRUCT_CODES == list(CONSTRUCTS)
    assert {c["code"]: c["name"] for c in scale.CONSTRUCTS} == CONSTRUCTS
    assert [len(scale.item_codes(c)) for c in CONSTRUCTS] == [4, 6, 5, 3, 4, 5, 5]
    assert all(item["code"].startswith(item["construct"]) for item in scale.ITEMS)
    assert scale.MEAN_COLUMNS == {c: f"{c}_mean" for c in CONSTRUCTS}


def test_source_citation():
    assert "Chen, L., Wu, Q. and Jiang, L. (2022)" in scale.SOURCE and "10.3390/su14053004" in scale.SOURCE
    assert "Sustainability, 14(5), 3004" in scale.SOURCE and "Table A1" in scale.SOURCE
    assert "Dunlap" in scale.EC_ORIGIN and "56(3), 425–442" in scale.EC_ORIGIN


def test_response_format_is_seven_point_with_endpoint_labels_only():
    assert scale.RESPONSE_OPTIONS == [1, 2, 3, 4, 5, 6, 7]
    assert scale.RESPONSE_LABELS == {
        1: "1 – Strongly disagree", 2: "2", 3: "3", 4: "4", 5: "5", 6: "6", 7: "7 – Strongly agree",
    }
    assert [k for k, v in scale.RESPONSE_LABELS.items() if v != str(k)] == [1, 7]


def test_instruction():
    assert scale.INSTRUCTION == "Please rate your level of agreement with the following statements."


def test_survey_pages_cover_all_constructs_in_order():
    assert cfg.SURVEY_PAGES == [["EC", "EV"], ["EAF", "EAT", "ER"], ["PSC", "EPB"]]
    assert [c for p in cfg.SURVEY_PAGES for c in p] == scale.CONSTRUCT_CODES


def test_questions_render_from_items_without_codes_in_labels():
    qs = [q for p in cfg.SURVEY_PAGES for q in scale.questions(p)]
    assert [q["id"] for q in qs] == list(EXPECTED)
    assert [q["label"] for q in qs] == list(EXPECTED.values())
    assert all(q["type"] == "likert" and q["options"] == [1, 2, 3, 4, 5, 6, 7] for q in qs)
    assert all(q["labels"] == scale.RESPONSE_LABELS for q in qs)
    for q in qs:
        assert not any(code in q["label"] for code in CONSTRUCTS) and not any(n in q["label"] for n in CONSTRUCTS.values())


def test_attention_check_on_page_2():
    assert scale.ATTENTION_CHECK is True and cfg.ATTENTION_CHECK_PAGE == 2
    qs = scale.questions(cfg.SURVEY_PAGES[1], attention_check=True)
    ids = [q["id"] for q in qs]
    assert ids == ["EAF1", "EAF2", "EAF3", "EAF4", "EAF5", "EAT1", "ATTN", "EAT2", "EAT3",
                   "ER1", "ER2", "ER3", "ER4"]
    attn = qs[ids.index("ATTN")]
    assert attn["label"] == "For this statement, please select 1 – Strongly disagree."
    assert attn["options"] == [1, 2, 3, 4, 5, 6, 7]
    assert "ATTN" not in scale.ITEM_CODES
    assert scale.attention_passed(1) is True
    assert scale.attention_passed(3) is False
    assert scale.attention_passed(7) is False
    assert scale.attention_passed("") == ""


def test_construct_means_exclude_attention_check_and_require_all_items():
    base = {code: 4 for code in scale.ITEM_CODES}
    df = pd.DataFrame(
        [
            {**base, "EC1": 1, "EC2": 2, "EC3": 3, "EC4": 4, "ATTN": 7},
            {**base, "EV2": None, "PSC1": 7, "PSC2": 7, "PSC3": 6, "PSC4": 6, "PSC5": 5},
        ]
    )
    scored = add_scale_scores(df)
    assert scored.loc[0, "EC_mean"] == 2.5
    assert scored.loc[0, "EPB_mean"] == 4
    assert math.isnan(scored.loc[1, "EV_mean"])
    assert scored.loc[1, "PSC_mean"] == 6.2
    assert all(f"{c}_mean" in scored.columns for c in CONSTRUCTS)
    assert "EC_mean" not in df.columns  # input not modified


def test_means_skipped_for_data_without_scale():
    df = pd.DataFrame([{"participant_id": "x", "pre_knowledge": 3}])
    assert not any(c.endswith("_mean") for c in add_scale_scores(df).columns)
