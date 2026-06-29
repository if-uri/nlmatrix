"""Gen 3 must have teeth: the flawed engine (trusts the `reversible` flag) is
caught by the same invariants the honest engine passes.
"""
import gen3_reversible as g


def test_oracle_satisfies_all_invariants():
    cases = g.expand()
    assert len(cases) >= 10
    for c in cases:
        res = g.run_case(c, engine=g.execute)
        assert g.check(c, res) == [], f"{c['id']}: {g.check(c, res)}"


def test_partial_failure_restores_world():
    c = next(c for c in g.expand() if c["id"].startswith("fail-mid"))
    res = g.run_case(c, engine=g.execute)
    assert res["status"] == "failed"
    assert res["rolled_back"] and res["restored"] is True


def test_reversibility_lie_is_refused_and_rolled_back():
    c = next(c for c in g.expand() if c["id"].startswith("lie-second"))
    res = g.run_case(c, engine=g.execute)
    assert res["status"] == "lie-refused"
    assert res["restored"] is True
    assert any(b["reason"] == "reversible-without-inverse" for b in res["blocked"])


def test_non_reversible_is_gated():
    c = next(c for c in g.expand() if c["id"].startswith("nonrev"))
    res = g.run_case(c, engine=g.execute)
    assert res["status"] == "blocked"
    assert g.check(c, res) == []


# --- the flawed architecture must be CAUGHT -----------------------------------
def test_flawed_engine_lets_the_lie_through():
    c = next(c for c in g.expand() if c["id"].startswith("lie-first"))
    res = g.run_case(c, engine=g.buggy_execute)
    viol = g.check(c, res)
    assert any("reversibility-lie" in x for x in viol), \
        "flag-trusting engine recorded a command with no inverse; checker must flag it"


def test_flawed_engine_leaves_residue_on_failure():
    c = next(c for c in g.expand() if c["id"].startswith("fail-mid"))
    res = g.run_case(c, engine=g.buggy_execute)
    viol = g.check(c, res)
    assert any("recovery" in x for x in viol), \
        "flag-trusting engine did not roll back; world left mutated, checker must flag it"
