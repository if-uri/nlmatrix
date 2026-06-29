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


def is_planner_error(envelope: dict) -> bool:
    if envelope.get("planner_error"):
        return True
    routing = envelope.get("routing", {}) or {}
    text = str(routing.get("violations") or routing.get("blockedSteps") or envelope.get("error") or "")
    return "planner-error" in text


def needs_selection_class(case: dict, env_state: dict, envelope: dict) -> str | None:
    """Classify a typed selection prompt as justified or unjustified.

    Autonomy is not "never ask". It is "resolve when intent + state are sufficient,
    ask when they are not". A bare screenshot request with three monitors is a justified
    selection. A request anchored on an existing Chrome window, an explicit monitor, a
    single available monitor, an all-monitor scope, or a remembered preference is not.
    """
    if envelope_kind(envelope) != "needs-selection":
        return None
    monitors = env_state.get("monitors") or []
    ids = [m.get("id") for m in monitors]
    hint = case.get("plan_hint") or {}
    scope = str(hint.get("scope") or "").lower()
    monitor = hint.get("monitor")
    anchor = hint.get("anchor")
    preferences = env_state.get("preferences") or {}

    if scope in {"all", "all-monitors", "desktop"}:
        return "unjustified"
    if monitor is not None:
        return "unjustified"
    if len(ids) == 1:
        return "unjustified"
    if anchor and env_state.get(f"{anchor}_on_monitor") is not None:
        return "unjustified"
    pref = preferences.get("screen.capture.default")
    if pref in ids:
        return "unjustified"
    return "justified"


def check_portable(case: dict, env_state: dict, envelope: dict) -> list[str]:
    """Check invariants that are meaningful on a live/current environment.

    This deliberately does NOT assert the metamorphic fixture's expected kind or
    exact monitor. Those expectations belong to the offline oracle. Portable
    checks answer a different question: if the real system produced a response,
    is it internally valid and grounded in the environment it reported?
    """
    v: list[str] = []
    ids = [m["id"] for m in env_state["monitors"]]
    kind = envelope_kind(envelope)

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
        # universal #4: result must not be an ungrounded implicit default ---
        if src in (None, "default") and mon in (0, None):
            v.append("resolution: silent/empty monitor default on result")

    elif kind == "needs-selection":
        ns = envelope.get("needsSelection", {})
        opt = sorted(o.get("value") for o in ns.get("options", []))
        if opt != sorted(ids):
            v.append(f"needs-selection: options {opt} != inventory {sorted(ids)}")
        if needs_selection_class(case, env_state, envelope) == "unjustified":
            v.append(
                "needs-selection-unjustified: intent/state was sufficient; "
                "planner should resolve or reject instead of asking"
            )

    return v


def check_fixture_expectation(case: dict, env_state: dict, envelope: dict) -> list[str]:
    """Check the synthetic metamorphic expectation for the offline oracle.

    These checks may be intentionally too strong for a real machine whose live
    environment does not match the case fixture.
    """
    v: list[str] = []
    exp = case["expect"]
    kind = envelope_kind(envelope)
    r = envelope.get("routing", {})
    if kind != exp["kind"]:
        v.append(f"kind: expected {exp['kind']} got {kind}")

    if kind == "result":
        cap = envelope.get("results", {}).get("capture", {}).get("result", {})
        mon = cap.get("monitor")
        em = exp.get("monitor")
        if em == "chrome":
            if mon != env_state.get("chrome_on_monitor"):
                v.append(f"anchor: captured {mon} != chrome monitor "
                         f"{env_state.get('chrome_on_monitor')}")
        elif em is not None and mon != em:
            v.append(f"monitor: expected {em} got {mon}")
        if exp.get("scope") == "all" and mon is not None:
            v.append(f"scope: scope-all but captured single monitor {mon}")

    elif kind == "reject":
        want = exp.get("reason")
        if want and not _reason_matches(str(want), r.get("violations", [])):
            v.append(f"reject: reason mismatch, want {want}, got {r.get('violations')}")

    return v


def check(case: dict, env_state: dict, envelope: dict) -> list[str]:
    return check_portable(case, env_state, envelope) + check_fixture_expectation(case, env_state, envelope)
