"""Gen 4 - router as a function of live state.

Obala bledna architekture: "routing decydowany raz i cache'owany". Taki router
robi snapshot srodowiska na poczatku flow i pozniej wykonuje kroki tak, jakby
CDP, node i monitory nie mogly zmienic stanu. To wyglada poprawnie w prostych
read-only testach, ale pada gdy `ensure` ozywia CDP, monitor znika przed
capture albo node staje sie offline po planie.

Niezmienniki:
  - po udanym `ensure` capture browser musi uzyc powierzchni CDP, nie starego
    fallbacku monitorowego;
  - capture przez CDP wolno wykonac tylko gdy CDP jest zywe w chwili dispatch;
  - capture monitora wolno wykonac tylko gdy monitor istnieje w chwili dispatch;
  - node offline przed krokiem blokuje krok, nie wykonuje go na starym snapshotcie.

Uruchom:  python3 gen4_state_router.py
Testy:    python3 -m pytest test_gen4.py -q

Hak urirun: router accept per-krok, cdp/session/command/ensure,
cdp/session/query/ready, env/query/inventory, dispatch_uri.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any


@dataclass(frozen=True)
class State:
    node_online: bool = True
    cdp_alive: bool = False
    ensure_ok: bool = True
    monitors: tuple[int, ...] = (1, 2)


def _state(data: dict | State) -> State:
    if isinstance(data, State):
        return data
    return State(
        node_online=bool(data.get("node_online", True)),
        cdp_alive=bool(data.get("cdp_alive", False)),
        ensure_ok=bool(data.get("ensure_ok", True)),
        monitors=tuple(data.get("monitors", (1, 2))),
    )


def _apply_event(state: State, event: dict | None) -> State:
    if not event:
        return state
    updates: dict[str, Any] = {}
    for key in ("node_online", "cdp_alive", "ensure_ok"):
        if key in event:
            updates[key] = bool(event[key])
    if "monitors" in event:
        updates["monitors"] = tuple(event["monitors"])
    return replace(state, **updates)


def _capture_event(surface: str, state: State, **extra) -> dict:
    return {
        "step": "capture",
        "surface": surface,
        "nodeOnlineAtDispatch": state.node_online,
        "cdpAliveAtDispatch": state.cdp_alive,
        "monitorsAtDispatch": list(state.monitors),
        **extra,
    }


def _block(reason: str, trace: list[dict], state: State) -> dict:
    return {"status": "blocked", "reason": reason, "trace": trace, "final": state}


def _ensure_cdp(state: State, trace: list[dict]) -> tuple[State, dict | None]:
    if not state.node_online:
        return state, _block("node-offline", trace, state)
    trace.append({"step": "ensure_cdp", "ok": state.ensure_ok, "nodeOnlineAtDispatch": state.node_online})
    if not state.ensure_ok:
        return state, _block("cdp-unreachable", trace, state)
    return replace(state, cdp_alive=True), None


def route_and_execute(case: dict) -> dict:
    """Honest stateful router: re-evaluate the live state before every action."""
    state = _apply_event(_state(case["initial"]), case.get("events", {}).get("after_plan"))
    intent = case["intent"]
    trace: list[dict] = []

    if intent["kind"] == "browser_capture":
        if not state.cdp_alive:
            state, blocked = _ensure_cdp(state, trace)
            if blocked:
                return blocked
        state = _apply_event(state, case.get("events", {}).get("before_capture"))
        if not state.node_online:
            return _block("node-offline", trace, state)
        if not state.cdp_alive:
            state, blocked = _ensure_cdp(state, trace)
            if blocked:
                return blocked
        trace.append(_capture_event("cdp", state))
        return {"status": "ok", "reason": "cdp-capture", "trace": trace, "final": state}

    if intent["kind"] == "monitor_capture":
        monitor = int(intent["monitor"])
        state = _apply_event(state, case.get("events", {}).get("before_capture"))
        if not state.node_online:
            return _block("node-offline", trace, state)
        if monitor not in state.monitors:
            return _block("monitor-unavailable", trace, state)
        trace.append(_capture_event("monitor", state, monitor=monitor))
        return {"status": "ok", "reason": "monitor-capture", "trace": trace, "final": state}

    return _block("unknown-intent", trace, state)


def buggy_cached_router(case: dict) -> dict:
    """Flawed architecture: route once from the initial snapshot and never re-check.

    The state may mutate (ensure succeeds, monitor detaches, node goes offline), but the
    dispatch decision keeps using the initial diagnosis.
    """
    snapshot = _state(case["initial"])
    state = _apply_event(snapshot, case.get("events", {}).get("after_plan"))
    intent = case["intent"]
    trace: list[dict] = []

    if intent["kind"] == "browser_capture":
        if not snapshot.node_online:
            return _block("node-offline", trace, state)
        planned_with_dead_cdp = not snapshot.cdp_alive
        if planned_with_dead_cdp:
            trace.append({"step": "ensure_cdp", "ok": state.ensure_ok,
                          "nodeOnlineAtDispatch": state.node_online})
            if not state.ensure_ok:
                return _block("cdp-unreachable", trace, state)
            state = replace(state, cdp_alive=True)
        state = _apply_event(state, case.get("events", {}).get("before_capture"))
        if planned_with_dead_cdp:
            # Stale fallback: the router never reconsiders that CDP became available.
            monitor = snapshot.monitors[0] if snapshot.monitors else None
            trace.append(_capture_event("monitor", state, monitor=monitor))
            return {"status": "ok", "reason": "stale-monitor-fallback",
                    "trace": trace, "final": state}
        # Stale optimistic CDP capture: ignores CDP/node changes after planning.
        trace.append(_capture_event("cdp", state))
        return {"status": "ok", "reason": "stale-cdp-capture", "trace": trace, "final": state}

    if intent["kind"] == "monitor_capture":
        monitor = int(intent["monitor"])
        if monitor not in snapshot.monitors:
            return _block("monitor-unavailable", trace, state)
        state = _apply_event(state, case.get("events", {}).get("before_capture"))
        trace.append(_capture_event("monitor", state, monitor=monitor))
        return {"status": "ok", "reason": "stale-monitor-capture",
                "trace": trace, "final": state}

    return _block("unknown-intent", trace, state)


def expand() -> list[dict]:
    return [
        {
            "id": "cdp-live-direct",
            "intent": {"kind": "browser_capture"},
            "initial": {"node_online": True, "cdp_alive": True, "monitors": [1, 2]},
            "expect": {"status": "ok", "reason": "cdp-capture", "surface": "cdp", "ensures": 0},
        },
        {
            "id": "cdp-dead-ensure-then-cdp",
            "intent": {"kind": "browser_capture"},
            "initial": {"node_online": True, "cdp_alive": False, "ensure_ok": True, "monitors": [1, 2]},
            "expect": {"status": "ok", "reason": "cdp-capture", "surface": "cdp", "ensures": 1},
        },
        {
            "id": "cdp-dead-ensure-fails",
            "intent": {"kind": "browser_capture"},
            "initial": {"node_online": True, "cdp_alive": False, "ensure_ok": False, "monitors": [1, 2]},
            "expect": {"status": "blocked", "reason": "cdp-unreachable", "captures": 0},
        },
        {
            "id": "cdp-dies-before-capture",
            "intent": {"kind": "browser_capture"},
            "initial": {"node_online": True, "cdp_alive": True, "ensure_ok": True, "monitors": [1, 2]},
            "events": {"before_capture": {"cdp_alive": False}},
            "expect": {"status": "ok", "reason": "cdp-capture", "surface": "cdp", "ensures": 1},
        },
        {
            "id": "node-offline-before-capture",
            "intent": {"kind": "browser_capture"},
            "initial": {"node_online": True, "cdp_alive": True, "monitors": [1, 2]},
            "events": {"before_capture": {"node_online": False}},
            "expect": {"status": "blocked", "reason": "node-offline", "captures": 0},
        },
        {
            "id": "monitor-live",
            "intent": {"kind": "monitor_capture", "monitor": 2},
            "initial": {"node_online": True, "monitors": [1, 2]},
            "expect": {"status": "ok", "reason": "monitor-capture", "surface": "monitor", "monitor": 2},
        },
        {
            "id": "monitor-detached-before-capture",
            "intent": {"kind": "monitor_capture", "monitor": 2},
            "initial": {"node_online": True, "monitors": [1, 2]},
            "events": {"before_capture": {"monitors": [1]}},
            "expect": {"status": "blocked", "reason": "monitor-unavailable", "captures": 0},
        },
        {
            "id": "node-offline-at-start",
            "intent": {"kind": "browser_capture"},
            "initial": {"node_online": False, "cdp_alive": True, "monitors": [1, 2]},
            "expect": {"status": "blocked", "reason": "node-offline", "captures": 0},
        },
    ]


def _captures(result: dict) -> list[dict]:
    return [e for e in result.get("trace", []) if e.get("step") == "capture"]


def _ensures(result: dict) -> list[dict]:
    return [e for e in result.get("trace", []) if e.get("step") == "ensure_cdp"]


def check(case: dict, result: dict) -> list[str]:
    v: list[str] = []
    exp = case["expect"]
    captures = _captures(result)
    if result.get("status") != exp.get("status"):
        v.append(f"status: expected {exp.get('status')} got {result.get('status')}")
    if result.get("reason") != exp.get("reason"):
        v.append(f"reason: expected {exp.get('reason')} got {result.get('reason')}")
    if "captures" in exp and len(captures) != exp["captures"]:
        v.append(f"captures: expected {exp['captures']} got {len(captures)}")
    if "ensures" in exp and len(_ensures(result)) != exp["ensures"]:
        v.append(f"ensures: expected {exp['ensures']} got {len(_ensures(result))}")
    if captures:
        cap = captures[-1]
        if "surface" in exp and cap.get("surface") != exp["surface"]:
            v.append(f"surface: expected {exp['surface']} got {cap.get('surface')}")
        if "monitor" in exp and cap.get("monitor") != exp["monitor"]:
            v.append(f"monitor: expected {exp['monitor']} got {cap.get('monitor')}")
        # TEETH: every capture must be legal in the state at dispatch time.
        if not cap.get("nodeOnlineAtDispatch"):
            v.append("stale-node-reachability: captured while node was offline")
        if cap.get("surface") == "cdp" and not cap.get("cdpAliveAtDispatch"):
            v.append("stale-cdp-capture: captured via CDP while CDP was dead")
        if cap.get("surface") == "monitor" and cap.get("monitor") not in cap.get("monitorsAtDispatch", []):
            v.append(f"stale-monitor-domain: captured monitor {cap.get('monitor')} "
                     f"not in {cap.get('monitorsAtDispatch')}")
    if case["id"] == "cdp-dead-ensure-then-cdp" and captures:
        if captures[-1].get("surface") != "cdp":
            v.append("stale-cdp-diagnosis: ensure made CDP live but router kept monitor fallback")
    return v


def run_case(case: dict, engine=route_and_execute) -> dict:
    return engine(case)


def main() -> int:
    cases = expand()
    passed = 0
    for c in cases:
        res = run_case(c)
        viol = check(c, res)
        ok = not viol
        passed += ok
        cap = _captures(res)[-1] if _captures(res) else {}
        mark = "✓" if ok else "✗"
        print(f"{mark} {c['id']:30s} status={res['status']:8s} "
              f"reason={res['reason']:22s} surface={str(cap.get('surface')):7s}")
        for x in viol:
            print(f"      - {x}")
    print(f"\nRESULT: {passed}/{len(cases)} state-router cases satisfy all invariants")
    return 0 if passed == len(cases) else 1


if __name__ == "__main__":
    raise SystemExit(main())
