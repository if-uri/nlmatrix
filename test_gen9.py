"""Gen 9 must have teeth: a global (fingerprint-blind) preference store is caught
by the same per-fingerprint invariant the honest store passes — a preference
remembered under one environment must not auto-run under another.
"""
import gen9_preference_memory as g


def test_honest_session_satisfies_all_invariants():
    assert g.check(g.run(g.Session())) == []


def test_preference_reused_only_at_matching_fingerprint():
    results = g.run(g.Session())
    by_id = dict(zip([s["id"] for s in g.scenario()], results))
    assert by_id["reuse-same-fp"]["action"] == "auto-run" and by_id["reuse-same-fp"]["monitor"] == 3
    assert by_id["different-fp-asks"]["action"] == "ask"


# --- the flawed architecture must be CAUGHT -----------------------------------
def test_global_preference_leaks_across_fingerprints():
    results = g.run(g.BuggySession())
    viol = g.check(results)
    assert any("preference-leak" in x for x in viol), \
        "global preference store auto-ran at a non-matching fingerprint; checker must flag it"


def test_buggy_session_diverges_at_different_fingerprint():
    results = g.run(g.BuggySession())
    by_id = dict(zip([s["id"] for s in g.scenario()], results))
    # honest asks here; the global store wrongly auto-runs the dock preference
    assert by_id["different-fp-asks"]["action"] == "auto-run"
