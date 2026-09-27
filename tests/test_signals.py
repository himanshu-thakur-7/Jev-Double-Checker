import pytest

from doubletake.data import stage_messages
from doubletake.signals import amounts, detect, domains, edit_distance, has_hard

MSGS = {m.id: m for m in stage_messages()}


def kinds(mid):
    m = MSGS[mid]
    flags, biller = detect(m.sender, m.text)
    return {f.kind for f in flags}, flags, biller


def test_hero_s01_gets_the_three_mockup_flags():
    k, flags, biller = kinds("S01")
    labels = [f.label for f in flags]
    assert biller.id == "bescom"
    assert any(l.startswith("Threat within hours: “disconnection at 9:30 PM tonight”") for l in labels)
    assert "Unknown link: bescom-bbps.in" in labels
    assert "Unregistered sender: VK-BESCMS" in labels


@pytest.mark.parametrize("mid", ["G01", "G02", "G03", "G04", "G05", "G06"])
def test_real_bills_have_no_hard_flags(mid):
    _, flags, biller = kinds(mid)
    assert biller is not None and not has_hard(flags), [f.label for f in flags]


@pytest.mark.parametrize("mid,kind", [("H3", "amount"), ("H4", "payee_change"), ("H5", "injection"),
                                      ("S07", "lookalike_link"), ("S08", "unknown_upi"), ("S06", "fee_for_refund"),
                                      ("H2", "lookalike_link")])
def test_hero_and_scam_specific_flags(mid, kind):
    k, _, _ = kinds(mid)
    assert kind in k


def test_autopay_info_on_icici():
    k, flags, _ = kinds("N01")
    assert "autopay" in k and not has_hard(flags)


def test_helpers():
    assert edit_distance("BESCMS", "BESCOM") == 2
    assert amounts("Rs.1,240.00 and ₹ 386") == [1240.0, 386.0]
    assert domains("pay at bescom-bbps.in/pay or airtel.in.bill-pay.co/1") == ["bescom-bbps.in", "airtel.in.bill-pay.co"]


def test_scam_recall_of_flags():
    """Every scam carries at least one flag; flags alone are evidence, not the whole decision."""
    for m in MSGS.values():
        if m.label == "scam":
            flags, _ = detect(m.sender, m.text)
            assert flags, m.id
