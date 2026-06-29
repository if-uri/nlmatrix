"""Invariants for LIVE runs. Three tiers:

  check_invariants        env-INDEPENDENT; must hold for ANY response
  check_self_consistency  relations computable from the SAME response
  expected_from_prompt    outcome computable from live env for some phrasings

Everything not assertable live is recorded, not asserted (the live twin is fixed
by the machine; fixture-controlled absolutes belong to the offline oracle).
"""
from __future__ import annotations

import json

ALL_SCOPES = {"all", "all-monitors", "desktop"}
FOCUS_URI_SUFFIX = "/window/command/focus"


def _inventory_ids(adapted):
    dom = (adapted.get("twin_inventory", {}) or {}).get("domains", {}) or {}
    return [o.get("value") for o in dom.get("env:monitors.id", []) or []]


def kind(adapted):
    if adapted.get("planner_error"):
        return "planner-error"
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

    if adapted.get("execute") is False and adapted.get("artifactEvidence"):
        v.append(f"dry-run-effect: execute=false response contains artifact evidence "
                 f"{adapted.get('artifactEvidence')}")

    v += _dataflow(adapted)
    v += _idempotent_flow_shape(adapted)
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


def _stable_json(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _idempotent_flow_shape(adapted) -> list[str]:
    """Catch duplicate executable steps that a normalizer should have collapsed.

    This is deliberately narrow: only identical native window-focus commands with the same
    payload and dependencies are flagged. That is the stale-process/recall failure observed
    in production; distinct focus commands remain legal.
    """
    v: list[str] = []
    seen: dict[tuple[str, str, tuple[str, ...]], str] = {}
    steps = (adapted.get("flow", {}) or {}).get("steps", []) or []
    for s in steps:
        uri = str(s.get("uri") or "")
        if not uri.endswith(FOCUS_URI_SUFFIX):
            continue
        key = (
            uri,
            _stable_json(s.get("payload") or {}),
            tuple(str(dep) for dep in (s.get("depends_on") or [])),
        )
        sid = str(s.get("id") or "")
        prev = seen.get(key)
        if prev is not None:
            v.append(f"idempotence: duplicate focus step {sid} repeats {prev} "
                     "(normalizer should collapse equivalent focus commands)")
        else:
            seen[key] = sid
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


def check_correlation(prompt_meta, adapted, request_no_llm) -> list[str]:
    """Correlation honesty: the response must be the answer to THIS request.

    Asserts ``response.prompt == request.prompt`` — a mismatch means a response was bound to the
    wrong request (a correlation-id leak, not a UI cosmetic). ``noLlm`` is only asserted when the
    envelope actually echoes it; today it does not, so an absent value is recorded, not failed
    (record-don't-assert) — the gap itself is that the resolved mode is not verifiable from the
    response, which is an urirun-side improvement, not a test failure."""
    v: list[str] = []
    req = str(prompt_meta.get("intent") or "").strip()
    resp = adapted.get("response_prompt")
    if resp is not None and str(resp).strip() != req:
        v.append(f"correlation: response.prompt {str(resp).strip()!r} != request {req!r} "
                 f"(answer bound to the wrong request)")
    rnl = adapted.get("response_noLlm")
    if rnl is not None and bool(rnl) != bool(request_no_llm):
        v.append(f"correlation: response.noLlm {rnl} != request {request_no_llm}")
    return v


def needs_selection_class(prompt_meta, adapted) -> "str | None":
    """Classify a needs-selection as 'justified' or 'unjustified' (or None when not a selection).

    Autonomy is: resolve when intent + state suffice; ASK when they do not. So not every
    needs-selection is a defect:

    * justified  — the intent carries no disambiguating info (bare 'screenshot' with >1 monitor and
      no stored preference). Asking is correct; silently picking a monitor here is a regression.
    * unjustified — the intent anchors on an app/window the user named ('the monitor with chrome')
      which uniquely determines the monitor, but the planner asked instead of resolving it via
      window/query/list -> capture(monitor_from). ONLY this is a defect / the autonomy gap.

    The unjustified count is the target to drive DOWN via the LLM planner (which reads action_space
    and derives the window-list step), not via hard-coding anchor phrases."""
    if kind(adapted) != "needs-selection":
        return None
    anchored = (prompt_meta.get("phrasing") == "anchor"
                or bool((prompt_meta.get("plan_hint") or {}).get("anchor"))
                or bool(prompt_meta.get("anchor")))
    return "unjustified" if anchored else "justified"


def check_needs_selection_autonomy(prompt_meta, adapted) -> list[str]:
    cls = needs_selection_class(prompt_meta, adapted)
    if cls != "unjustified":
        return []
    return [
        "needs-selection-unjustified: intent had an anchor; planner should resolve "
        "with state/action_space before asking"
    ]


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
        elif ids and n is not None and k not in ("reject", "needs-selection"):
            v.append(f"explicit: monitor {n} not in inventory {ids} but kind={k} "
                     f"(expected reject/needs-selection)")
    elif phr == "all" and cap:
        if cap.get("monitor") is not None and str(cap.get("scope") or "").lower() not in ALL_SCOPES:
            v.append(f"all: expected all-scope, got single monitor {cap.get('monitor')}")
    return v
