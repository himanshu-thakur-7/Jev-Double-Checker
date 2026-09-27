from collections import Counter

from doubletake.data import gold_messages, registry, stage_messages


def test_stage_set_shape():
    msgs = stage_messages()
    assert len(msgs) == 30
    assert len({m.id for m in msgs}) == 30
    gold = Counter(m.label for m in gold_messages())
    assert gold == {"scam": 8, "bill": 6, "none": 10}


def test_labels_match_expected_actions():
    for m in stage_messages():
        assert {"bill": "pay", "scam": "hold", "none": "ignore"}[m.label] == m.expected_action, m.id


def test_billers_referenced_exist():
    reg = registry()
    for m in stage_messages():
        if m.biller:
            assert reg.by_id(m.biller), m.id


def test_hero_uses_unregistered_header_and_unknown_domain():
    reg = registry()
    s01 = next(m for m in stage_messages() if m.id == "S01")
    assert s01.sender not in reg.all_headers
    assert "bescom-bbps.in" not in reg.all_domains
    assert "AX-BESCOM" in reg.all_headers


def test_context_is_compact():
    ctx = registry().context()
    assert len(ctx["billers_on_file"]) == 8 and "Rahul" in ctx["family"]
