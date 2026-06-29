"""Gen 4 must have teeth: a router that caches the initial environment snapshot
is caught by the same invariants the honest stateful router passes.
"""
import gen4_state_router as g


def test_oracle_satisfies_all_invariants():
    cases = g.expand()
    assert len(cases) >= 8
    for c in cases:
        res = g.run_case(c, engine=g.route_and_execute)
        assert g.check(c, res) == [], f"{c['id']}: {g.check(c, res)}"


def test_cdp_dead_then_ensure_replans_to_cdp():
    c = next(c for c in g.expand() if c["id"] == "cdp-dead-ensure-then-cdp")
    res = g.run_case(c, engine=g.route_and_execute)
    captures = [e for e in res["trace"] if e.get("step") == "capture"]
    assert res["status"] == "ok"
    assert captures[-1]["surface"] == "cdp"
    assert len([e for e in res["trace"] if e.get("step") == "ensure_cdp"]) == 1


def test_cdp_dies_before_capture_is_recovered_by_reensure():
    c = next(c for c in g.expand() if c["id"] == "cdp-dies-before-capture")
    res = g.run_case(c, engine=g.route_and_execute)
    assert res["status"] == "ok"
    assert len([e for e in res["trace"] if e.get("step") == "ensure_cdp"]) == 1
    assert g.check(c, res) == []


def test_monitor_detach_blocks_not_stale_capture():
    c = next(c for c in g.expand() if c["id"] == "monitor-detached-before-capture")
    res = g.run_case(c, engine=g.route_and_execute)
    assert res["status"] == "blocked"
    assert res["reason"] == "monitor-unavailable"
    assert not [e for e in res["trace"] if e.get("step") == "capture"]


# --- the flawed architecture must be CAUGHT -----------------------------------
def test_cached_router_keeps_monitor_fallback_after_ensure():
    c = next(c for c in g.expand() if c["id"] == "cdp-dead-ensure-then-cdp")
    res = g.run_case(c, engine=g.buggy_cached_router)
    viol = g.check(c, res)
    assert any("stale-cdp-diagnosis" in x for x in viol), \
        "cached router kept the pre-ensure monitor fallback; checker must flag it"


def test_cached_router_captures_dead_cdp():
    c = next(c for c in g.expand() if c["id"] == "cdp-dies-before-capture")
    res = g.run_case(c, engine=g.buggy_cached_router)
    viol = g.check(c, res)
    assert any("stale-cdp-capture" in x for x in viol), \
        "cached router captured through CDP after CDP died; checker must flag it"


def test_cached_router_ignores_monitor_detach():
    c = next(c for c in g.expand() if c["id"] == "monitor-detached-before-capture")
    res = g.run_case(c, engine=g.buggy_cached_router)
    viol = g.check(c, res)
    assert any("stale-monitor-domain" in x for x in viol), \
        "cached router captured a detached monitor; checker must flag it"


def test_cached_router_ignores_node_offline_before_capture():
    c = next(c for c in g.expand() if c["id"] == "node-offline-before-capture")
    res = g.run_case(c, engine=g.buggy_cached_router)
    viol = g.check(c, res)
    assert any("stale-node-reachability" in x for x in viol), \
        "cached router captured after target node went offline; checker must flag it"
