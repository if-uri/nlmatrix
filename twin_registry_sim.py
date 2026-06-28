"""Reference oracle for the NL test-matrix.

This is the *correct* behaviour, encoded once. Shapes mirror the live execution
trace (the kvm capture envelope): twin inventory, the capture contract's
env-enum domain, routing acceptance, and the resolution order
explicit -> data-flow -> sole -> remembered -> needs-selection.

The real system plugs in where `reference_plan` + `resolve_and_execute` sit
(see README). The property checker (properties.py) runs against EITHER output.
"""
from __future__ import annotations

from typing import Any

# --- the capture contract domain, copied verbatim from the live trace ---------
CAPTURE_DOMAIN = {
    "monitor": {
        "type": "enum",
        "domain": "env:monitors.id",
        "optional": True,
        "preference": "screen.capture.default",
        "skipWhen": {"scope": ["all", "all-monitors", "desktop"]},
        "emptyValues": [0, ""],
        "allValue": -1,
    }
}

# tiny registry: uri -> declared effect (mirrors route.meta.contract.effect) ----
REGISTRY = {
    "kvm://host/window/query/list": {"effect": "query", "reversible": True},
    "kvm://host/screen/query/capture": {
        "effect": "query",
        "reversible": False,
        "domains": CAPTURE_DOMAIN,
    },
}


def make_env(monitors: list[dict], chrome_on_monitor: int | None = None,
             cdp: bool = True, fingerprint: str = "env-301de3e353",
             preference: int | None = None) -> dict:
    """Build a twin-state fixture. `preference` is the remembered
    screen.capture.default for THIS fingerprint (None = not remembered here)."""
    mons = [{"id": m["id"], "connector": m.get("connector", f"DP-{m['id']}"),
             "primary": m.get("primary", False)} for m in monitors]
    return {
        "fingerprint": fingerprint,
        "monitors": mons,
        "cdp_endpoints": ([{"id": "127.0.0.1:9222", "running": True}] if cdp else []),
        "chrome_on_monitor": chrome_on_monitor,
        "preferences": {"screen.capture.default": preference},
    }


def _ids(env: dict) -> list[int]:
    return [m["id"] for m in env["monitors"]]


def reference_plan(plan_hint: dict, env: dict) -> dict:
    """Structured-intent + twin_state -> flow. The oracle plans deterministically
    from `plan_hint`; a real LLM would plan from the NL `intent` string instead."""
    anchor = plan_hint.get("anchor")
    scope = plan_hint.get("scope")
    explicit = plan_hint.get("monitor")
    steps: list[dict] = []
    cap: dict[str, Any] = {}
    if scope:
        cap["scope"] = scope
    if anchor == "chrome":
        steps.append({"id": "list_windows", "uri": "kvm://host/window/query/list",
                      "payload": {"app": "chrome"}, "depends_on": []})
        cap["monitor_from"] = "list_windows.result.value.selected.monitor"
    if explicit is not None:
        cap["monitor"] = explicit
    steps.append({"id": "capture", "uri": "kvm://host/screen/query/capture",
                  "payload": cap,
                  "depends_on": (["list_windows"] if anchor == "chrome" else [])})
    return {"steps": steps}


def _resolve_capture(payload: dict, env: dict, ids: list[int]) -> dict:
    """The env-enum resolution gate. Order is the whole point."""
    domain = CAPTURE_DOMAIN["monitor"]
    scope = str(payload.get("scope") or "").lower()
    # 0. skipWhen scope -> capture all, no monitor needed
    if scope in {s.lower() for s in domain["skipWhen"]["scope"]}:
        return {"monitor": None, "scope": scope or "all", "source": "scope-all"}
    # 1. explicit payload value (validated against inventory)
    if "monitor" in payload and payload["monitor"] not in domain["emptyValues"]:
        m = payload["monitor"]
        if m not in ids:
            return {"kind": "reject", "reason": "monitor-not-in-inventory"}
        return {"monitor": m, "scope": "monitor", "source": "explicit"}
    # 2. data-flow reference (resolved from the window-list step at runtime)
    if "monitor_from" in payload:
        m = env.get("chrome_on_monitor")
        if m is None:
            return {"kind": "needs-selection", "reason": "anchor-window-not-found"}
        if m not in ids:
            return {"kind": "reject", "reason": "monitor-not-in-inventory"}
        return {"monitor": m, "scope": "monitor", "source": "dataflow"}
    # 3. sole option
    if len(ids) == 1:
        return {"monitor": ids[0], "scope": "monitor", "source": "single"}
    # 4. remembered preference for THIS fingerprint
    pref = (env.get("preferences") or {}).get(domain["preference"])
    if pref in ids:
        return {"monitor": pref, "scope": "monitor", "source": "remembered"}
    # 5. ambiguous -> typed needs-selection
    return {"kind": "needs-selection", "reason": "ambiguous-monitor"}


def _inventory_block(env: dict) -> dict:
    return {
        "fingerprint": env["fingerprint"],
        "domains": {
            "env:monitors.id": [
                {"value": m["id"], "label": m["connector"], "primary": m.get("primary", False)}
                for m in env["monitors"]
            ],
            "env:cdp_endpoints.id": [{"value": c["id"]} for c in env["cdp_endpoints"]],
        },
        "monitors": env["monitors"],
    }


def _needs_selection(res: dict, env: dict, routing_steps: list[dict]) -> dict:
    return {
        "ok": False,
        "needsSelection": {
            "parameter": "monitor",
            "domain": "env:monitors.id",
            "options": [{"value": m["id"], "label": m["connector"]} for m in env["monitors"]],
            "reason": res.get("reason"),
            "fingerprint": env["fingerprint"],
        },
        "routing": {"accepted": True, "blockedSteps": [], "violations": [], "steps": routing_steps},
        "results": {},
        "twin_inventory": _inventory_block(env),
    }


def resolve_and_execute(flow: dict, env: dict) -> dict:
    """Simulate router accept + env-enum resolution + execute -> envelope."""
    ids = _ids(env)
    routing_steps: list[dict] = []
    accepted, violations, blocked = True, [], []
    capture_result: dict | None = None

    for step in flow["steps"]:
        uri = step["uri"]
        reg = REGISTRY.get(uri)
        if reg is None:
            accepted = False
            blocked.append({"uri": uri, "reason": "no-route"})
            routing_steps.append({"uri": uri, "ok": False, "effect": None,
                                  "contract_effect": None, "safe": False})
            continue
        effect = reg["effect"]
        routing_steps.append({"uri": uri, "ok": True, "effect": effect,
                              "safe": effect == "query", "contract_effect": effect})
        if uri.endswith("/screen/query/capture"):
            res = _resolve_capture(step["payload"], env, ids)
            if res.get("kind") == "needs-selection":
                return _needs_selection(res, env, routing_steps)
            if res.get("kind") == "reject":
                accepted = False
                blocked.append({"uri": uri, "reason": res["reason"]})
                violations.append(res["reason"])
                continue
            capture_result = res

    envelope = {
        "ok": accepted and capture_result is not None,
        "routing": {"accepted": accepted, "blockedSteps": blocked,
                    "violations": violations, "steps": routing_steps},
        "results": {},
        "twin_inventory": _inventory_block(env),
        "fingerprint": env["fingerprint"],
    }
    if capture_result is not None:
        envelope["results"]["capture"] = {
            "ok": True, "invokedUri": "kvm://host/screen/query/capture",
            "result": {"kind": "screenshot",
                       "monitor": capture_result.get("monitor"),
                       "scope": capture_result.get("scope", "monitor"),
                       "source": capture_result.get("source")},
        }
    return envelope


def run_case_reference(case: dict) -> dict:
    """Default executor: the oracle. Swap for the real planner/router via run.py."""
    env = make_env(**case["env_spec"])
    flow = reference_plan(case["plan_hint"], env)
    return resolve_and_execute(flow, env), env
