from doubletake.data import stage_messages
from doubletake.engine import QIDS, Engine, TAU, questions
from doubletake.jev import JevResult
from doubletake.llm import SecondOpinion

MSGS = {m.id: m for m in stage_messages()}


def answers(pay=0.9, scam=0.1, genuine=0.9, choice_override=None):
    rest = (1 - pay) / 2
    probs = {"pay": pay, "hold": rest, "ignore": rest}
    ch = choice_override or max(probs, key=probs.get)
    a = {f"a{i}": {"type": "choice", "choice": ch, "probabilities": probs, "confidence": 0.9} for i in range(5)}
    a |= {"s0": {"type": "noul", "noul": scam}, "s1": {"type": "noul", "noul": scam},
          "g0": {"type": "noul", "noul": genuine}, "g1": {"type": "noul", "noul": genuine}}
    return a


class FakeJev:
    def __init__(self, per_rewrite):
        self.per_rewrite, self.calls = per_rewrite, []

    async def ask(self, state, qs):
        i = len(self.calls)
        self.calls.append(state)
        return JevResult("jev-1.13.0", self.per_rewrite[i % len(self.per_rewrite)], 400, 50, 80.0, 400 * 0.042e-6)

    async def aclose(self): ...


class FakeLLM:
    def __init__(self, verdict="legitimate", action="pay"):
        self.v, self.a = verdict, action

    async def review(self, sender, text, ctx):
        return SecondOpinion(self.v, self.a, 0.1 if self.v == "legitimate" else 0.9, "Routine reminder.",
                             "gpt-6-sol", 300, 40, 1400.0, 0.001)

    async def aclose(self): ...


async def run(mid, per_rewrite, llm=None):
    return await Engine(jev=FakeJev(per_rewrite), llm=llm or FakeLLM()).examine(MSGS[mid])


def test_questions_are_nine_per_call():
    assert list(questions()) == QIDS and len(QIDS) == 9


async def test_consistent_pay_is_paid_in_all_modes():
    ex = await run("G01", [answers()])
    assert {m: d["action"] for m, d in ex.decisions.items()} == {"jev_only": "pay", "jev_llm": "pay", "double_take": "pay"}
    assert ex.reasks == 35 and ex.brittleness <= TAU and ex.alert is None
    assert len(ex.grid) == 4 and all(len(r) == 9 for r in ex.grid)
    assert ex.grid[0][0]["base"] and ex.cost["jev_calls"] == 4


async def test_brittle_pay_is_held_only_by_double_take():
    # base rewrite confidently says pay; the rewrites disagree
    ex = await run("G02", [answers(0.9), answers(0.3, scam=0.6, genuine=0.4), answers(0.35, scam=0.55, genuine=0.45),
                           answers(0.4, scam=0.5, genuine=0.5)])
    assert ex.decisions["jev_only"]["action"] == "pay"
    assert ex.decisions["jev_llm"]["action"] == "pay"
    assert ex.decisions["double_take"]["action"] == "hold"
    assert "re-asks disagreed with paying" in ex.decisions["double_take"]["reason"]
    assert "confidence alone would have paid this" in ex.decisions["double_take"]["reason"]
    assert ex.alert and ex.alert["title"] == "Held for Rahul"


async def test_hard_flag_holds_even_when_consistent():
    ex = await run("H5", [answers()])  # injection + lookalike link
    assert ex.decisions["jev_only"]["action"] == "pay"
    assert ex.decisions["double_take"]["action"] == "hold"
    assert "instructions to the assistant" in ex.decisions["double_take"]["reason"]


async def test_llm_objection_holds_in_jev_llm():
    ex = await run("G01", [answers()], llm=FakeLLM("scam", "hold"))
    assert ex.decisions["jev_llm"]["action"] == "hold"
    assert ex.decisions["double_take"]["action"] == "hold"


async def test_base_ignore_is_ignored_everywhere():
    ex = await run("N02", [answers(0.05, choice_override="ignore")])
    assert {d["action"] for d in ex.decisions.values()} == {"ignore"}


async def test_state_carries_rewrite_and_household():
    fj = FakeJev([answers()])
    await Engine(jev=fj, llm=FakeLLM()).examine(MSGS["S01"])
    texts = [c["sms"]["text"] for c in fj.calls]
    assert texts[0] == MSGS["S01"].text and len(set(texts)) == 4
    assert "billers_on_file" in fj.calls[0]["household"]
