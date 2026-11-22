import pytest

from cases.adversarial import ATTACKS, make_adversarial
from cases.builder import CLEAR_TYPES
from cases.split import build_split
from tests.test_cases import synth_pools


def test_each_attack_keeps_the_clean_id():
    # @criterion C6
    res = build_split(synth_pools())
    clean = next(c for c in res["dev"] if c["type"] == "delay_above")
    assert len(ATTACKS) == 6
    texts = set()
    for a in ATTACKS:
        adv = make_adversarial(clean, a)
        assert adv["clean_case_id"] == clean["case_id"]
        assert adv["case_id"] == f"{clean['case_id']}-adv-{a}"
        assert adv["type"] == "adversarial" and adv["attack"] == a
        assert adv["message"]["constructed"] is True
        assert adv["message"]["text"].startswith(clean["message"]["text"])
        assert (
            adv["facts"] == clean["facts"] and adv["bts_flight"] == clean["bts_flight"]
        )
        texts.add(adv["message"]["text"])
    assert len(texts) == 6
    with pytest.raises(ValueError):
        make_adversarial(clean, "bribe")


def test_adversarial_cases_come_from_clear_cases_of_the_same_side():
    # @criterion C6
    res = build_split(synth_pools())
    for side in ("dev", "test"):
        by_id = {c["case_id"]: c for c in res[side]}
        advs = [c for c in res[side] if c["type"] == "adversarial"]
        assert {c["attack"] for c in advs} == set(ATTACKS)
        for a in advs:
            assert by_id[a["clean_case_id"]]["type"] in CLEAR_TYPES
