"""Invariant checks. Returns [] if a case passes, else a list of violations.

These are properties that must hold regardless of HOW the planner phrased the
plan. They are checked against the reference oracle AND against the real system.
A property that never fails is useless, so test_nlmatrix.py feeds deliberately
broken envelopes and asserts these fire.
"""
from __future__ import annotations


def envelope_kind(env: dict) -> str:
    if env.get("needsSelection"):
        return "needs-selection"
    r = env.get("routing", {})
    if not r.get("accepted", False):
        return "reject"
    if env.get("results", {}).get("capture"):
        return "result"
    return "empty"


def _reason_matches(want: str, got: object) -> bool:
    text = str(got)
    if want in text:
        return True
    if want == "monitor-not-in-inventory" and "env-domain-invalid" in text:
        return True
    return False


def check(case: dict, env_state: dict, envelope: dict) -> list[str]:
    v: list[str] = []
    exp = case["expect"]
    ids = [m["id"] for m in env_state["monitors"]]
    kind = envelope_kind(envelope)

    # case expectation -----------------------------------------------------
    if kind != exp["kind"]:
        v.append(f"kind: expected {exp['kind']} got {kind}")

    r = envelope.get("routing", {})

    # universal #1: accepted <=> no blocked & no violations ----------------
    if r.get("accepted") and (r.get("blockedSteps") or r.get("violations")):
        v.append("gate: accepted=true but blocked/violations present")

    # universal #2: effect honesty + read-only safety ----------------------
    for s in r.get("steps", []):
        if s.get("ok") and s.get("contract_effect") is not None:
            if s.get("effect") != s.get("contract_effect"):
                v.append(f"effect-honesty: {s['uri']} effect={s.get('effect')} "
                         f"!= contract={s.get('contract_effect')}")
            if s.get("effect") == "query" and not s.get("safe"):
                v.append(f"safety: query route {s['uri']} not marked safe")

    if kind == "result":
        cap = envelope.get("results", {}).get("capture", {}).get("result", {})
        mon = cap.get("monitor")
        src = cap.get("source")
        # universal #3: captured monitor grounded in inventory -------------
        if src != "scope-all" and mon is not None and mon not in ids:
            v.append(f"grounding: captured monitor {mon} not in inventory {ids}")
        # expected monitor -------------------------------------------------
        em = exp.get("monitor")
        if em == "chrome":
            if mon != env_state.get("chrome_on_monitor"):
                v.append(f"anchor: captured {mon} != chrome monitor "
                         f"{env_state.get('chrome_on_monitor')}")
        elif em is not None and mon != em:
            v.append(f"monitor: expected {em} got {mon}")
        # universal #4: scope-all must not collapse to one monitor ---------
        if exp.get("scope") == "all" and mon is not None:
            v.append(f"scope: scope-all but captured single monitor {mon}")
        # universal #5: ambiguity must never silently default --------------
        if em not in ("chrome",) and exp.get("scope") != "all":
            if src in (None, "default") and mon in (0, None):
                v.append("resolution: silent/empty monitor default on result")

    elif kind == "needs-selection":
        ns = envelope.get("needsSelection", {})
        opt = sorted(o.get("value") for o in ns.get("options", []))
        if opt != sorted(ids):
            v.append(f"needs-selection: options {opt} != inventory {sorted(ids)}")

    elif kind == "reject":
        want = exp.get("reason")
        if want and not _reason_matches(str(want), r.get("violations", [])):
            v.append(f"reject: reason mismatch, want {want}, got {r.get('violations')}")

    return v
