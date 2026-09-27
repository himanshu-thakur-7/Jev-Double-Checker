import pytest

from doubletake.data import stage_messages
from doubletake.perturb import REWRITES, all_rewrites, facts, noisy, plain, reshuffle

MSGS = stage_messages()


@pytest.mark.parametrize("m", MSGS, ids=[m.id for m in MSGS])
def test_rewrites_preserve_facts(m):
    base = facts(m.text)
    for r, t in all_rewrites(m.text).items():
        got = facts(t)
        assert base <= got, (r, base - got)


def test_deterministic():
    t = MSGS[0].text
    assert all_rewrites(t) == all_rewrites(t)


def test_rewrites_differ_from_original():
    s01 = next(m for m in MSGS if m.id == "S01").text
    rw = all_rewrites(s01)
    assert set(rw) == set(REWRITES)
    assert rw["R0"] == s01
    assert len({rw[r] for r in REWRITES}) == 4


def test_plain_removes_shouting():
    assert plain("Dear Consumer, BESCOM ALERT: Pay NOW!!! Visit bescom-bbps.in") == "BESCOM Alert: Pay.\nVisit bescom-bbps.in"


def test_reshuffle_keeps_all_sentences():
    t = "First part here. Second part 12. Third part at x.in/pay."
    out = reshuffle(t)
    assert out != t and sorted(out.split(". ")) != [] and all(p in out for p in ["First part here", "Second part 12", "x.in/pay"])


def test_noisy_never_touches_numbers():
    t = "Pay Rs.1,240.00 for Acct 1234567890 at bescom-bbps.in/pay tonight please consumer"
    out = noisy(t)
    for tok in ["Rs.1,240.00", "1234567890", "bescom-bbps.in/pay"]:
        assert tok in out
