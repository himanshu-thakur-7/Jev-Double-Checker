from doubletake import cache
from doubletake.data import Message


class FakeEngine:
    def __init__(self):
        self.n = 0

    async def examine(self, msg):
        self.n += 1

        class Ex:
            def to_dict(_):
                return {"message": msg.model_dump(), "n": self.n}
        return Ex()


async def test_cache_roundtrip(tmp_path):
    m = Message(id="X1", sender="AX-BESCOM", text="hello")
    eng = FakeEngine()
    a, hit = await cache.examine_cached(eng, m, root=tmp_path)
    assert not hit and a["n"] == 1
    b, hit = await cache.examine_cached(eng, m, root=tmp_path)
    assert hit and b["n"] == 1 and eng.n == 1
    c, hit = await cache.examine_cached(eng, m, refresh=True, root=tmp_path)
    assert not hit and c["n"] == 2
    assert len(list(tmp_path.glob("X1-*.json"))) == 1


def test_key_changes_with_text():
    a = Message(id="X", sender="S", text="a")
    b = Message(id="X", sender="S", text="b")
    assert cache.key(a) != cache.key(b)
