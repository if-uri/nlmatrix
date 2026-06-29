"""Gen 2 must have teeth: a resolver that silently defaults missing data-flow
references is caught by the same invariants the honest resolver passes.
"""
import gen2_data_flow as g


def test_oracle_satisfies_all_invariants():
    cases = g.expand()
    assert len(cases) >= 6
    for c in cases:
        res = g.run_case(c, engine=g.resolve)
        assert g.check(c, res) == [], f"{c['id']}: {g.check(c, res)}"


def test_monitor_from_resolves_to_producer_value():
    c = next(c for c in g.expand() if c["id"] == "resolved-ok")
    res = g.run_case(c, engine=g.resolve)
    capture = next(s for s in res["steps"] if s["id"] == "capture")
    assert capture["payload"]["monitor"] == 3


def test_null_source_blocks_not_defaults():
    c = next(c for c in g.expand() if c["id"] == "source-null")
    res = g.run_case(c, engine=g.resolve)
    assert res["status"] == "blocked"
    assert res["reason"] == "ref-source-null"


def test_missing_dependency_blocks():
    c = next(c for c in g.expand() if c["id"] == "missing-dep")
    res = g.run_case(c, engine=g.resolve)
    assert res["status"] == "blocked"
    assert res["reason"] == "ref-missing-dependency"


# --- the flawed architecture must be CAUGHT -----------------------------------
def test_buggy_resolver_silently_defaults_null_source():
    c = next(c for c in g.expand() if c["id"] == "source-null")
    res = g.run_case(c, engine=g.buggy_resolve)
    viol = g.check(c, res)
    assert any("silent-default" in x for x in viol), \
        "buggy resolver substituted a default monitor; checker must flag it"


def test_buggy_resolver_ignores_missing_dependency():
    c = next(c for c in g.expand() if c["id"] == "missing-dep")
    res = g.run_case(c, engine=g.buggy_resolve)
    viol = g.check(c, res)
    assert any("silent-default" in x for x in viol), \
        "buggy resolver ignored dependency wiring; checker must flag it"
