"""Gen 7 must have teeth: the sentiment-based verdict (is_destructive) is caught
by the same invariants the contract-based verdict passes. The destructiveness of
an operation is a function of its contract, not of how the prompt is phrased.
"""
import gen7_effect_honesty as g


def test_oracle_satisfies_all_invariants():
    cases = g.expand()
    assert len(cases) >= 8
    for c in cases:
        res = g.run_case(c, engine=g.verdict)
        assert g.check(c, res) == [], f"{c['id']}: {g.check(c, res)}"


def test_honest_verdict_is_phrasing_invariant():
    assert g.metamorphic_invariance(g.verdict) == []


def test_gentle_phrasing_of_a_delete_is_still_destructive():
    c = next(c for c in g.expand() if "posprz" in c["prompt"])
    assert g.run_case(c, engine=g.verdict)["destructive"] is True


def test_scary_phrasing_of_a_read_is_not_destructive():
    c = next(c for c in g.expand() if c["uri"].endswith("/dir/query/list") and "zniszcz" in c["prompt"])
    assert g.run_case(c, engine=g.verdict)["destructive"] is False


# --- the flawed architecture must be CAUGHT -----------------------------------
def test_sentiment_verdict_varies_by_phrasing():
    drift = g.metamorphic_invariance(g.buggy_verdict)
    assert drift, "sentiment-based verdict must vary across phrasings of the same op"


def test_gentle_euphemism_lets_a_destructive_op_through():
    c = next(c for c in g.expand() if "posprz" in c["prompt"])
    viol = g.check(c, g.run_case(c, engine=g.buggy_verdict))
    assert any("effect-from-sentiment" in x for x in viol), \
        "sentiment engine allowed a real delete phrased gently; checker must flag it"


def test_scary_word_blocks_a_benign_read():
    c = next(c for c in g.expand() if c["uri"].endswith("/dir/query/list") and "zniszcz" in c["prompt"])
    viol = g.check(c, g.run_case(c, engine=g.buggy_verdict))
    assert any("effect-from-sentiment" in x for x in viol), \
        "sentiment engine blocked a benign read phrased scarily; checker must flag it"
