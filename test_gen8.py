"""Gen 8 must have teeth: an engine that trusts `ok:true` as 'done' is caught by
the same verify(state) invariant the honest engine passes — phantom-success and
silent-stop-on-failure are both flagged.
"""
import gen8_verification as g


def test_oracle_satisfies_all_invariants():
    cases = g.expand()
    assert len(cases) >= 5
    for c in cases:
        res = g.run_case(c, engine=g.execute)
        assert g.check(c, res) == [], f"{c['id']}: {g.check(c, res)}"


def test_phantom_success_is_not_done():
    c = next(c for c in g.expand() if c["id"] == "phantom-success")
    res = g.run_case(c, engine=g.execute)
    assert res["status"] == "not-done" and res["verified"] is False


def test_failure_yields_recovery():
    c = next(c for c in g.expand() if c["id"] == "step-failure")
    res = g.run_case(c, engine=g.execute)
    assert res["status"] == "failed" and res["recovery"]


# --- the flawed architecture must be CAUGHT -----------------------------------
def test_flag_trusting_engine_reports_phantom_as_done():
    c = next(c for c in g.expand() if c["id"] == "phantom-success")
    res = g.run_case(c, engine=g.buggy_execute)
    viol = g.check(c, res)
    assert any("phantom-success" in x for x in viol), \
        "ok-trusting engine reported a phantom step as done; checker must flag it"


def test_flag_trusting_engine_stops_silently_on_failure():
    c = next(c for c in g.expand() if c["id"] == "step-failure")
    res = g.run_case(c, engine=g.buggy_execute)
    viol = g.check(c, res)
    assert any("silent-stop" in x for x in viol), \
        "ok-trusting engine stopped on failure with no recovery; checker must flag it"
