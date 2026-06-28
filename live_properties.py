"""Invariants for LIVE runs. Three tiers:

  check_invariants        env-INDEPENDENT; must hold for ANY response
  check_self_consistency  relations computable from the SAME response
  expected_from_prompt    outcome computable from live env for some phrasings

Everything not assertable live is recorded, not asserted (the live twin is fixed
by the machine; fixture-controlled absolutes belong to the offline oracle).
"""
from __future__ import annotations

ALL_SCOPES = {"all", "all-monitors", "desktop"}


def _inventory_ids(adapted):
    dom = (adapted.get("twin_inventory", {}) or {}).get("domains", {}) or {}
    return [o.get("value") for o in dom.get("env:monitors.id", []) or []]


def kind(adapted):
    if adapted.get("needsSelection"):
        return "needs-selection"
    if not adapted.get("routing", {}).get("accepted", False):
        return "reject"
    if adapted.get("results", {}).get("capture"):
        return "result"
    return "planned"  # accepted, nothing executed (execute=0)


def check_invariants(adapted) -> list[str]:
    v: list[str] = []
    r = adapted.get("routing", {})

    # gate: accepted <=> nothing blocked
    if r.get("accepted") and (r.get("blockedSteps") or r.get("violations")):
        v.append("gate: accepted=true but blocked/violations present")

    # effect honesty + read-only safety
    for s in r.get("steps", []):
        if s.get("ok") and s.get("contract_effect") is not None:
            if s.get("effect") != s.get("contract_effect"):
                v.append(f"effect-honesty: {s['uri']} effect={s.get('effect')} "
                         f"!= contract={s.get('contract_effect')}")
            if s.get("effect") == "query" and s.get("safe") is False:
                v.append(f"safety: query {s['uri']} not marked safe")

    ids = _inventory_ids(adapted)
    cap = adapted.get("results", {}).get("capture", {}).get("result")
    if cap:
        mon = cap.get("monitor")
        scope = str(cap.get("scope") or "").lower()
        if scope not in ALL_SCOPES and mon is not None and ids and mon not in ids:
            v.append(f"grounding: captured monitor {mon} not in inventory {ids}")
        if scope not in ALL_SCOPES and mon in (0, None):
            v.append("resolution: result with no monitor and no all-scope (silent default?)")

    if adapted.get("needsSelection"):
        opt = [o.get("value") for o in adapted["needsSelection"].get("options", []) or []]
        clean = sorted(x for x in opt if x is not None)
        if ids and clean != sorted(ids):
            v.append(f"needs-selection: options {opt} != inventory {ids}")

    v += _dataflow(adapted)
    return v


def _dataflow(adapted) -> list[str]:
    v = []
    steps = (adapted.get("flow", {}) or {}).get("steps", []) or []
    by_id = {s.get("id"): s for s in steps}
    order = [s.get("id") for s in steps]
    for s in steps:
        ref = (s.get("payload", {}) or {}).get("monitor_from")
        if isinstance(ref, str) and "." in ref:
            src = ref.split(".", 1)[0]
            sid = s.get("id")
            if src not in by_id:
                v.append(f"dataflow: {sid} references unknown step {src}")
            elif order.index(src) >= order.index(sid):
                v.append(f"dataflow: {sid} references {src} which is not earlier")
            elif src not in (s.get("depends_on") or []):
                v.append(f"dataflow: {sid} refs {src} but it is not in depends_on")
    return v


def check_self_consistency(adapted) -> list[str]:
    v = []
    cap = adapted.get("results", {}).get("capture", {}).get("result")
    sel = adapted.get("selected_window_monitor")
    if cap and sel is not None and cap.get("monitor") is not None:
        if str(cap.get("scope") or "").lower() not in ALL_SCOPES and cap.get("monitor") != sel:
            v.append(f"anchor: captured monitor {cap.get('monitor')} "
                     f"!= selected window monitor {sel}")
    return v


def expected_from_prompt(prompt_meta, adapted) -> list[str]:
    v = []
    phr = prompt_meta.get("phrasing")
    ids = _inventory_ids(adapted)
    k = kind(adapted)
    cap = adapted.get("results", {}).get("capture", {}).get("result")
    if phr == "explicit":
        n = prompt_meta.get("monitor")
        if n in ids:
            if cap and cap.get("monitor") != n:
                v.append(f"explicit: asked monitor {n}, captured {cap.get('monitor')}")
        elif n is not None and k not in ("reject", "needs-selection"):
            v.append(f"explicit: monitor {n} not in inventory {ids} but kind={k} "
                     f"(expected reject/needs-selection)")
    elif phr == "all" and cap:
        if cap.get("monitor") is not None and str(cap.get("scope") or "").lower() not in ALL_SCOPES:
            v.append(f"all: expected all-scope, got single monitor {cap.get('monitor')}")
    return v
