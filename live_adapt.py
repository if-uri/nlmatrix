"""Adapt a LIVE urirun chat envelope into the property-checker shape.

The real envelope shape is known exactly (it is the trace returned by chat_ask):
routing.steps carry `effect` and `route.meta.contract.effect`; results are keyed
by step id and carry `invokedUri`; twin inventory rides under
results["twin:inventory:host"]. We read facts FROM the response — no fixtures.
"""
from __future__ import annotations

CAPTURE_URI = "kvm://host/screen/query/capture"
WINDOW_LIST_URI = "kvm://host/window/query/list"
INVENTORY_KEY = "twin:inventory:host"
ALL_SCOPES = {"all", "all-monitors", "desktop"}


def _artifact_evidence(envelope: dict) -> list[str]:
    evidence: list[str] = []

    def walk(value, path: str = "$") -> None:
        if isinstance(value, dict):
            kind = str(value.get("kind") or "").lower()
            for key in ("path", "artifactPath", "pngbase64", "pngBase64"):
                if value.get(key):
                    if key.lower() == "pngbase64" or "screenshot" in kind or str(value.get(key)).endswith((".png", ".jpg", ".jpeg")):
                        evidence.append(f"{path}.{key}")
            for key, child in value.items():
                walk(child, f"{path}.{key}")
        elif isinstance(value, list):
            for idx, child in enumerate(value):
                walk(child, f"{path}[{idx}]")

    # Route metadata contains contract examples and output schemas with sample
    # paths. Those are documentation, not evidence that a dry-run produced an
    # artifact. Only execution result surfaces can prove a side effect.
    walk(envelope.get("results") or {}, "$.results")
    walk(envelope.get("attachments") or [], "$.attachments")
    walk(envelope.get("artifacts") or [], "$.artifacts")
    return sorted(set(evidence))


def _result_by_uri(results: dict, uri: str):
    for _id, r in (results or {}).items():
        if isinstance(r, dict) and r.get("invokedUri") == uri:
            return r
    return None


def adapt(envelope: dict) -> dict:
    results = envelope.get("results", {}) or {}
    routing = envelope.get("routing", {}) or {}

    steps = []
    for s in routing.get("steps", []) or []:
        route = s.get("route", {}) or {}
        contract = (route.get("meta", {}) or {}).get("contract", {}) or {}
        steps.append({
            "uri": s.get("uri"),
            "ok": s.get("ok", False),
            "effect": s.get("effect"),
            "contract_effect": contract.get("effect"),
            "safe": route.get("safe"),
        })

    out = {
        "ok": envelope.get("ok", False),
        "execute": envelope.get("execute"),
        "routing": {
            "accepted": routing.get("accepted", False),
            "blockedSteps": routing.get("blockedSteps", []) or [],
            "violations": routing.get("violations", []) or [],
            "steps": steps,
        },
        "results": {},
        "needsSelection": envelope.get("needsSelection"),
        "flow": envelope.get("flow", {}) or {},
        "artifactEvidence": _artifact_evidence(envelope),
    }

    inv = results.get(INVENTORY_KEY, {}) or {}
    out["twin_inventory"] = {
        "fingerprint": inv.get("fingerprint"),
        "domains": inv.get("domains", {}) or {},
        "monitors": inv.get("monitors", []) or [],
    }

    cap = _result_by_uri(results, CAPTURE_URI)
    if cap and cap.get("ok"):
        cr = cap.get("result", {}) or {}
        out["results"]["capture"] = {
            "ok": True,
            "result": {"monitor": cr.get("monitor"), "scope": cr.get("scope"),
                       "outputConnector": cr.get("outputConnector"),
                       "width": cr.get("width"), "height": cr.get("height")},
        }

    wl = _result_by_uri(results, WINDOW_LIST_URI)
    if wl and wl.get("ok"):
        sel = (wl.get("result", {}) or {}).get("selected", {}) or {}
        out["selected_window_monitor"] = sel.get("monitor")

    # Planner/infra failure is NOT a gate reject: the chat never produced a plan to judge
    # (e.g. the LLM is rate-limited and heuristic fallback is disabled). Surface it so the
    # harness records it as an infra skip instead of green-washing it as a passing "reject".
    err = envelope.get("error") or {}
    gen = envelope.get("generator") or {}
    recovery = envelope.get("recovery") or []
    out["planner_error"] = bool(
        envelope.get("ok") is False and (
            gen.get("intent") == "planner-recovery"
            or "planner failed" in str(err.get("message") or "").lower()
            or any("planner/command/make" in str((r or {}).get("uri") or "") for r in recovery)
        )
    )
    out["error_message"] = str(err.get("message") or "")[:120] if out["planner_error"] else ""

    # Correlation honesty: the response must echo THIS request's prompt (a request<->response
    # leak would attribute an answer to the wrong intent). noLlm is surfaced too — currently the
    # envelope does NOT echo it, so the checker records (does not assert) when it is absent.
    out["response_prompt"] = envelope.get("prompt")
    out["response_noLlm"] = envelope.get("noLlm", envelope.get("no_llm"))

    return out


def resolved_facts(adapted: dict) -> str:
    """The one-line resolved facts your dashboard now shows in Copy MD."""
    cap = adapted.get("results", {}).get("capture", {}).get("result")
    if cap:
        bits = []
        if cap.get("monitor") is not None:
            bits.append(f"monitor={cap['monitor']}")
        if cap.get("outputConnector"):
            bits.append(f"output={cap['outputConnector']}")
        if cap.get("scope"):
            bits.append(f"scope={cap['scope']}")
        if cap.get("width") and cap.get("height"):
            bits.append(f"{cap['width']}x{cap['height']}")
        return " · ".join(bits) or "result"
    if adapted.get("needsSelection"):
        ns = adapted["needsSelection"]
        return f"needs-selection ({ns.get('reason') or 'choose'})"
    if not adapted["routing"]["accepted"]:
        why = adapted["routing"].get("violations") or adapted["routing"].get("blockedSteps")
        return f"reject: {why}"
    return "planned (execute=0)"
