from doubletake.redteam import variants
from doubletake.signals import detect


def test_variants_are_reproducible_and_flagged():
    v = variants()
    assert len(v) == 48 and len({x.id for x in v}) == 48
    assert [x.text for x in v] == [x.text for x in variants()]
    for x in v:  # every red-team variant keeps a checkable scam tell
        flags, _ = detect(x.sender, x.text)
        assert flags, x.id
