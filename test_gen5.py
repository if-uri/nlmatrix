"""Gen 5 must have teeth: the flawed router ("everything silently falls to host")
is caught by the same invariants the honest router passes.

The mutant IS the regression fixed in this session — a router that drops an
explicit `node:` selection to host and never blocks an unreachable target.
"""
import gen5_cross_target as g


def test_oracle_satisfies_all_invariants():
    cases = g.expand()
    assert len(cases) >= 8
    for c in cases:
        res = g.run_case(c, engine=g.route)
        assert g.check(c, res) == [], f"{c['id']}: {g.check(c, res)}"


def test_explicit_node_selection_wins_over_benign_prompt():
    c = next(c for c in g.expand() if c["id"] == "explicit-wins-benign-prompt")
    res = g.run_case(c, engine=g.route)
    assert res["runsOn"] == "lenovo" and res["status"] == "ok"


def test_unreachable_target_is_typed_block_not_host():
    c = next(c for c in g.expand() if c["id"] == "explicit-node-offline")
    res = g.run_case(c, engine=g.route)
    assert res["status"] == "blocked" and res["runsOn"] is None
    assert res["reason"] == "unreachable-node"


def test_stopped_service_blocks():
    c = next(c for c in g.expand() if c["id"] == "service-stopped")
    res = g.run_case(c, engine=g.route)
    assert res["status"] == "blocked" and res["reason"] == "service-stopped"


def test_host_default_only_without_explicit_node():
    c = next(c for c in g.expand() if c["id"] == "host-default-no-node")
    res = g.run_case(c, engine=g.route)
    assert res["runsOn"] == "host" and g.check(c, res) == []


# --- the flawed architecture must be CAUGHT -----------------------------------
def test_flawed_router_drops_explicit_node_to_host():
    c = next(c for c in g.expand() if c["id"] == "explicit-wins-benign-prompt")
    res = g.run_case(c, engine=g.buggy_route)
    viol = g.check(c, res)
    assert any("silent-host-fallback" in x for x in viol), \
        "host-falling router ran an explicit node on host; checker must flag it"


def test_flawed_router_does_not_block_unreachable():
    c = next(c for c in g.expand() if c["id"] == "explicit-node-offline")
    res = g.run_case(c, engine=g.buggy_route)
    viol = g.check(c, res)
    assert any("unreachable-not-blocked" in x for x in viol), \
        "host-falling router silently ran an unreachable target on host; checker must flag it"


def test_flawed_router_fails_the_mixed_target_case():
    # the exact shape of test_chat_ask_derives_nodes_from_node_targets
    c = next(c for c in g.expand() if c["id"] == "mixed-host-and-node")
    assert g.check(c, g.run_case(c, engine=g.route)) == []
    assert g.check(c, g.run_case(c, engine=g.buggy_route)) != []
