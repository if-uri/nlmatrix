"""The checker must have teeth. These tests prove:
  1. the generator produces >= 100 NL cases,
  2. the reference oracle satisfies every invariant on every case,
  3. the property checker FIRES on deliberately-broken envelopes (mutants).
"""
import copy

import properties
import transforms
import twin_registry_sim as sim


def test_generates_at_least_100():
    cases = transforms.expand()
    assert len(cases) >= 100
    intents = [c["intent"] for c in cases]
    assert all(intents)
    assert len(set(intents)) >= 40

    # The metamorphic point: the SAME words under a DIFFERENT twin state must
    # carry a DIFFERENT expected outcome. Assert such a pair exists (e.g. the
    # chrome-anchor phrasing is a `result` with chrome open and a
    # `needs-selection` with chrome closed).
    by_intent: dict[str, set] = {}
    for c in cases:
        by_intent.setdefault(c["intent"], set()).add(c["expect"]["kind"])
    assert any(len(kinds) >= 2 for kinds in by_intent.values()), \
        "expected metamorphic pairs: same NL, different outcome under different env"


def test_reference_oracle_satisfies_all_invariants():
    for c in transforms.expand():
        envelope, env = sim.run_case_reference(c)
        viol = properties.check(c, env, envelope)
        assert viol == [], f"{c['id']} ({c['intent']}): {viol}"


def _seed_case():
    return next(c for c in transforms.expand() if c["id"].startswith("anchor-3mon"))


def test_mutant_out_of_inventory_monitor_is_caught():
    c = _seed_case()
    envelope, env = sim.run_case_reference(c)
    bad = copy.deepcopy(envelope)
    bad["results"]["capture"]["result"]["monitor"] = 9  # not in inventory
    assert any("grounding" in x for x in properties.check(c, env, bad))


def test_mutant_effect_dishonesty_is_caught():
    c = _seed_case()
    envelope, env = sim.run_case_reference(c)
    bad = copy.deepcopy(envelope)
    # a query route mislabelled as command (the is_destructive class of bug)
    bad["routing"]["steps"][-1]["effect"] = "command"
    assert any("effect-honesty" in x for x in properties.check(c, env, bad))


def test_mutant_silent_default_on_ambiguous_is_caught():
    c = next(c for c in transforms.expand() if c["id"].startswith("ambiguous"))
    env = sim.make_env(**c["env_spec"])
    # a buggy planner that silently captures monitor 0 instead of asking
    bad = {
        "ok": True,
        "routing": {"accepted": True, "blockedSteps": [], "violations": [],
                    "steps": [{"uri": "kvm://host/screen/query/capture", "ok": True,
                               "effect": "query", "safe": True, "contract_effect": "query"}]},
        "results": {"capture": {"ok": True,
                                "result": {"kind": "screenshot", "monitor": 0, "source": "default"}}},
        "twin_inventory": sim._inventory_block(env),
    }
    viol = properties.check(c, env, bad)
    assert viol, "expected needs-selection; silent monitor=0 must violate"


def test_unjustified_needs_selection_is_caught_when_anchor_is_resolvable():
    c = _seed_case()
    env = sim.make_env(**c["env_spec"])
    bad = {
        "ok": False,
        "needsSelection": {
            "parameter": "monitor",
            "domain": "env:monitors.id",
            "options": [{"value": m["id"], "label": m["connector"]} for m in env["monitors"]],
            "reason": "ambiguous-monitor",
        },
        "routing": {"accepted": True, "blockedSteps": [], "violations": [],
                    "steps": [{"uri": "kvm://host/screen/query/capture", "ok": True,
                               "effect": "query", "safe": True, "contract_effect": "query"}]},
        "results": {},
        "twin_inventory": sim._inventory_block(env),
    }

    viol = properties.check_portable(c, env, bad)

    assert any("needs-selection-unjustified" in x for x in viol)


def test_anchor_closed_needs_selection_is_justified():
    c = next(c for c in transforms.expand() if c["id"].startswith("anchor-closed"))
    envelope, env = sim.run_case_reference(c)

    assert properties.needs_selection_class(c, env, envelope) == "justified"
    assert not any("needs-selection-unjustified" in x for x in properties.check_portable(c, env, envelope))


def test_mutant_preference_leak_across_fingerprint_is_caught():
    c = next(c for c in transforms.expand() if c["id"].startswith("fp-guard"))
    env = sim.make_env(**c["env_spec"])
    # a buggy system that applies a global preference ignoring fingerprint
    bad = {
        "ok": True,
        "routing": {"accepted": True, "blockedSteps": [], "violations": [],
                    "steps": [{"uri": "kvm://host/screen/query/capture", "ok": True,
                               "effect": "query", "safe": True, "contract_effect": "query"}]},
        "results": {"capture": {"ok": True,
                                "result": {"kind": "screenshot", "monitor": 2, "source": "remembered"}}},
        "twin_inventory": sim._inventory_block(env),
    }
    viol = properties.check(c, env, bad)
    assert any("kind" in x for x in viol), "preference must not leak across fingerprints"
