"""Gen 6 must have teeth: literal recall replay is caught by the same
invariants the honest recall-adaptation engine passes.
"""
import gen6_recall_adaptation as g


def test_oracle_satisfies_all_invariants():
    cases = g.expand()
    assert len(cases) >= 7
    for c in cases:
        res = g.run_case(c, engine=g.adapt_recall)
        assert g.check(c, res) == [], f"{c['id']}: {g.check(c, res)}"


def test_same_fingerprint_valid_reuse_is_allowed():
    c = next(c for c in g.expand() if c["id"] == "same-fingerprint-valid")
    res = g.run_case(c, engine=g.adapt_recall)
    assert res["status"] == "ok"
    assert res["monitor"] == 3
    assert res["reason"] == "same-fingerprint-reuse"


def test_drifted_fingerprint_reanchors_to_current_chrome_monitor():
    c = next(c for c in g.expand() if c["id"] == "drifted-fingerprint-reanchor")
    res = g.run_case(c, engine=g.adapt_recall)
    assert res["monitor"] == 2
    assert res["reason"] == "re-resolved-from-anchor"
    assert g._has_window_ref(res["flow"])


def test_closed_anchor_blocks_instead_of_replaying_stale_monitor():
    c = next(c for c in g.expand() if c["id"] == "anchor-window-closed")
    res = g.run_case(c, engine=g.adapt_recall)
    assert res["status"] == "blocked"
    assert res["reason"] == "anchor-window-not-found"


def test_old_preference_does_not_cross_fingerprint():
    c = next(c for c in g.expand() if c["id"] == "old-preference-does-not-leak")
    res = g.run_case(c, engine=g.adapt_recall)
    assert res["status"] == "blocked"
    assert res["monitor"] is None


# --- the flawed architecture must be CAUGHT -----------------------------------
def test_literal_recall_reuses_concrete_monitor_after_drift():
    c = next(c for c in g.expand() if c["id"] == "drifted-fingerprint-reanchor")
    res = g.run_case(c, engine=g.buggy_literal_recall)
    viol = g.check(c, res)
    assert any("literal-recall-across-fingerprint" in x for x in viol), \
        "literal recall reused concrete monitor after fingerprint drift; checker must flag it"
    assert any("stale-env-value" in x for x in viol), \
        "literal recall used monitor outside current inventory; checker must flag it"


def test_literal_recall_ignores_closed_anchor():
    c = next(c for c in g.expand() if c["id"] == "anchor-window-closed")
    res = g.run_case(c, engine=g.buggy_literal_recall)
    viol = g.check(c, res)
    assert any("literal-recall-across-fingerprint" in x for x in viol), \
        "literal recall executed even though anchor window was absent; checker must flag it"


def test_literal_recall_leaks_old_preference_across_fingerprint():
    c = next(c for c in g.expand() if c["id"] == "old-preference-does-not-leak")
    res = g.run_case(c, engine=g.buggy_literal_recall)
    viol = g.check(c, res)
    assert any("preference-fingerprint-leak" in x for x in viol), \
        "literal recall leaked preference across fingerprint; checker must flag it"


def test_literal_recall_fails_to_use_current_state_reference():
    c = next(c for c in g.expand() if c["id"] == "drifted-fingerprint-reanchor")
    res = g.run_case(c, engine=g.buggy_literal_recall)
    viol = g.check(c, res)
    assert any("missing-current-state-reference" in x for x in viol), \
        "adapted recall should have switched concrete monitor to monitor_from"
