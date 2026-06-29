"""Gen 10 must have teeth: an engine without an idempotency guard is caught by
the same invariant the honest engine passes — a repeated mutation must not double
the effect, and a repeated query must stay identical.
"""
import gen10_idempotence as g


def test_oracle_satisfies_all_invariants():
    cases = g.expand()
    assert len(cases) >= 4
    for c in cases:
        world, results = g.run_case(c, engine=g.execute)
        assert g.check(c, world, results) == [], f"{c['id']}: {g.check(c, world, results)}"


def test_repeated_mutation_fires_once():
    c = next(c for c in g.expand() if c["id"] == "repeat-mutation")
    world, _ = g.run_case(c, engine=g.execute)
    assert world["sent"] == 1


def test_distinct_keys_are_not_deduped():
    c = next(c for c in g.expand() if c["id"] == "distinct-mutations")
    world, _ = g.run_case(c, engine=g.execute)
    assert world["sent"] == 2


# --- the flawed architecture must be CAUGHT -----------------------------------
def test_guardless_engine_doubles_a_repeated_mutation():
    c = next(c for c in g.expand() if c["id"] == "repeat-mutation")
    world, results = g.run_case(c, engine=g.buggy_execute)
    viol = g.check(c, world, results)
    assert any("double-mutation" in x for x in viol), \
        "guardless engine sent twice for one repeated op; checker must flag it"


def test_guardless_engine_triples_on_three_clicks():
    c = next(c for c in g.expand() if c["id"] == "triple-repeat")
    world, results = g.run_case(c, engine=g.buggy_execute)
    assert world["sent"] == 3
    assert g.check(c, world, results) != []
