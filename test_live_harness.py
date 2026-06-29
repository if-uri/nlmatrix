"""Validate the LIVE harness against a REAL chat envelope (the user's trace).

Proves the adapter parses a real response and the live invariants hold on it,
plus that the checks catch deliberately-broken real-shaped envelopes. This is
the offline proof; live_run.py then points the same code at the running server.
"""
import copy
import json
import os

import live_adapt
import live_properties as lp

HERE = os.path.dirname(__file__)
FIXTURE = os.path.join(HERE, "fixtures", "trace_chrome_monitor.json")
if not os.path.exists(FIXTURE):
    FIXTURE = os.path.join(HERE, "trace_chrome_monitor.json")


def _load():
    with open(FIXTURE, encoding="utf-8") as fh:
        return json.load(fh)


def test_adapter_reads_real_envelope():
    a = live_adapt.adapt(_load())
    assert lp.kind(a) == "result"
    cap = a["results"]["capture"]["result"]
    assert cap["monitor"] == 3
    assert cap["outputConnector"] == "DP-1"
    assert cap["scope"] == "monitor"
    assert a["selected_window_monitor"] == 3
    facts = live_adapt.resolved_facts(a)
    assert "monitor=3" in facts and "output=DP-1" in facts and "scope=monitor" in facts


def test_real_envelope_satisfies_all_live_invariants():
    a = live_adapt.adapt(_load())
    viol = lp.check_invariants(a) + lp.check_self_consistency(a)
    assert viol == [], viol


def test_mutant_grounding_caught():
    env = _load()
    env["results"]["capture_chrome_monitor"]["result"]["monitor"] = 9  # not in inventory
    a = live_adapt.adapt(env)
    assert any("grounding" in x for x in lp.check_invariants(a))


def test_mutant_effect_dishonesty_caught():
    env = _load()
    # capture is the 2nd routing step; mislabel its effect as command
    env["routing"]["steps"][1]["effect"] = "command"
    a = live_adapt.adapt(env)
    assert any("effect-honesty" in x for x in lp.check_invariants(a))


def test_mutant_anchor_inconsistency_caught():
    env = _load()
    # window says chrome is on 3, but capture grabbed 2 -> self-consistency fails
    env["results"]["capture_chrome_monitor"]["result"]["monitor"] = 2
    a = live_adapt.adapt(env)
    assert any("anchor" in x for x in lp.check_self_consistency(a))


def test_mutant_dataflow_missing_dependency_caught():
    env = _load()
    env["flow"]["steps"][1]["depends_on"] = []  # ref without depends_on
    a = live_adapt.adapt(env)
    assert any("dataflow" in x for x in lp.check_invariants(a))


def test_mutant_duplicate_focus_step_caught():
    env = _load()
    env["flow"]["steps"] = [
        env["flow"]["steps"][0],
        {
            "id": "focus_list_chrome_windows",
            "uri": "kvm://host/window/command/focus",
            "payload": {"title": "chrome"},
            "depends_on": ["list_chrome_windows"],
        },
        {
            "id": "focus_list_chrome_windows_2",
            "uri": "kvm://host/window/command/focus",
            "payload": {"title": "chrome"},
            "depends_on": ["list_chrome_windows"],
        },
        env["flow"]["steps"][1],
    ]
    env["flow"]["steps"][3]["depends_on"] = [
        "focus_list_chrome_windows",
        "focus_list_chrome_windows_2",
        "list_chrome_windows",
    ]

    a = live_adapt.adapt(env)

    assert any("duplicate focus" in x for x in lp.check_invariants(a))


def test_mutant_dry_run_artifact_evidence_caught():
    env = _load()
    env["execute"] = False

    a = live_adapt.adapt(env)

    assert any("dry-run-effect" in x for x in lp.check_invariants(a))


def test_contract_examples_are_not_dry_run_artifact_evidence():
    env = {
        "execute": False,
        "routing": {
            "accepted": True,
            "steps": [{
                "ok": True,
                "uri": "kvm://host/screen/query/capture",
                "effect": "query",
                "route": {
                    "safe": True,
                    "meta": {
                        "contract": {
                            "effect": "query",
                            "examples": [{
                                "result": {
                                    "kind": "screenshot",
                                    "path": "/tmp/example.png",
                                },
                            }],
                        },
                    },
                },
            }],
        },
        "flow": {"steps": [{"id": "capture", "uri": "kvm://host/screen/query/capture"}]},
        "results": {},
        "attachments": [],
    }

    a = live_adapt.adapt(env)

    assert a["artifactEvidence"] == []
    assert not any("dry-run-effect" in x for x in lp.check_invariants(a))


def test_correlation_prompt_and_no_llm_are_asserted_when_echoed():
    env = _load()
    env["prompt"] = "jaka jest dzisiaj data"
    env["noLlm"] = False

    a = live_adapt.adapt(env)
    viol = lp.check_correlation(
        {"intent": "zrób zrzut ekranu"},
        a,
        request_no_llm=True,
    )

    assert any("response.prompt" in x for x in viol)
    assert any("response.noLlm" in x for x in viol)


def test_anchor_needs_selection_is_unjustified_live_gap():
    env = {
        "ok": False,
        "prompt": "zrób zrzut ekranu monitora, na którym jest chrome",
        "noLlm": True,
        "needsSelection": {
            "parameter": "monitor",
            "domain": "env:monitors.id",
            "options": [{"value": 1}, {"value": 2}, {"value": 3}],
            "reason": "ambiguous-monitor",
        },
        "routing": {"accepted": True, "blockedSteps": [], "violations": [], "steps": []},
        "results": {
            "twin:inventory:host": {
                "domains": {"env:monitors.id": [{"value": 1}, {"value": 2}, {"value": 3}]},
                "monitors": [{"id": 1}, {"id": 2}, {"id": 3}],
            },
        },
    }

    a = live_adapt.adapt(env)

    assert lp.needs_selection_class({"phrasing": "anchor"}, a) == "unjustified"
    assert any("needs-selection-unjustified" in x
               for x in lp.check_needs_selection_autonomy({"phrasing": "anchor"}, a))


def test_generic_needs_selection_is_justified_live_prompt():
    env = {
        "ok": False,
        "prompt": "zrób zrzut ekranu",
        "noLlm": True,
        "needsSelection": {
            "parameter": "monitor",
            "domain": "env:monitors.id",
            "options": [{"value": 1}, {"value": 2}, {"value": 3}],
            "reason": "ambiguous-monitor",
        },
        "routing": {"accepted": True, "blockedSteps": [], "violations": [], "steps": []},
        "results": {
            "twin:inventory:host": {
                "domains": {"env:monitors.id": [{"value": 1}, {"value": 2}, {"value": 3}]},
                "monitors": [{"id": 1}, {"id": 2}, {"id": 3}],
            },
        },
    }

    a = live_adapt.adapt(env)

    assert lp.needs_selection_class({"phrasing": "generic"}, a) == "justified"
    assert lp.check_needs_selection_autonomy({"phrasing": "generic"}, a) == []
