#!/usr/bin/env python3
"""Generate the NL matrix, run each case, check invariants, report.

  python3 run.py                 # all cases vs the reference oracle, with checks
  python3 run.py --list          # just print every generated NL line
  python3 run.py --json          # machine-readable per-case results
  python3 run.py --real          # run against the installed urirun (seam below)
  python3 run.py --mr relocate   # only one metamorphic family

Default executor is the reference oracle (twin_registry_sim). The point of the
oracle is to (a) prove the generator + checker are well-formed end to end and
(b) define the correct behaviour the real system is measured against.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import properties
import transforms
import twin_registry_sim as sim


ROOT = Path(__file__).resolve().parents[1]


def _ensure_real_paths() -> None:
    """Make sibling packages importable when this runner is executed from repo root."""
    for rel in (
        "urirun/adapters/python",
        "urirun-flow",
        "urirun-connector-router",
        "urirun-contract",
        "urirun-connectors-toolkit",
    ):
        path = str(ROOT / rel)
        if path not in sys.path:
            sys.path.insert(0, path)


def _real_routes() -> list[dict]:
    """Minimal route catalogue used by the metamorphic screenshot matrix.

    The payload schemas intentionally allow flow-DSL result references such as
    ``monitor_from`` because the real planner may use data-flow to bind a
    window's monitor at execution time.
    """
    capture_contract = {
        "effect": "query",
        "reversible": False,
        "domains": sim.CAPTURE_DOMAIN,
    }
    return [
        {
            "uri": "kvm://host/window/query/list",
            "node": "host",
            "safe": True,
            "kind": "query",
            "meta": {"contract": {"effect": "query", "reversible": True}},
            "inputSchema": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "app": {"type": "string"},
                    "title": {"type": "string"},
                },
            },
        },
        {
            "uri": "kvm://host/screen/query/capture",
            "node": "host",
            "safe": True,
            "kind": "query",
            "meta": {"contract": capture_contract},
            "inputSchema": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "base64": {"type": "boolean"},
                    "monitor": {"type": "integer"},
                    "monitor_from": {"type": "string"},
                    "scope": {"type": "string"},
                },
            },
        },
    ]


class _Memory:
    def __init__(self, env: dict):
        self.env = env

    def recall_preference(self, node: str, name: str, fingerprint: str) -> dict | None:
        if node != "host" or fingerprint != self.env.get("fingerprint"):
            return None
        value = (self.env.get("preferences") or {}).get(name)
        if value is None:
            return None
        return {"value": value, "fingerprint": fingerprint}


def _planner_environments(env: dict, inventory: dict) -> list[dict]:
    return [{
        "node": "host",
        "inventory": inventory,
        "domains": inventory.get("domains") or {},
        "profile": {
            "platform": "linux-wayland",
            "best": "cdp" if env.get("cdp_endpoints") else "screen",
            "monitors": env.get("monitors") or [],
            "cdp": {"reachable": bool(env.get("cdp_endpoints"))},
        },
    }]


def _resolve_capture_result(flow: dict, env: dict) -> tuple[dict | None, dict | None]:
    ids = [m["id"] for m in env.get("monitors") or []]
    for step in flow.get("steps") or []:
        if str(step.get("uri") or "").endswith("/screen/query/capture"):
            result = sim._resolve_capture(step.get("payload") or {}, env, ids)
            return step, result
    return None, None


def _routing_steps(acceptance: dict) -> list[dict]:
    report_steps = ((acceptance.get("report") or {}).get("steps") or [])
    out: list[dict] = []
    for step in report_steps:
        if not isinstance(step, dict):
            continue
        route = step.get("route") if isinstance(step.get("route"), dict) else {}
        contract = (route.get("meta") or {}).get("contract") or route.get("contract") or {}
        out.append({
            "uri": step.get("uri"),
            "ok": step.get("ok", True),
            "effect": step.get("effect"),
            "safe": bool(route.get("safe", step.get("effect") == "query")),
            "contract_effect": contract.get("effect"),
        })
    return out


def _reject_envelope(acceptance: dict, inventory: dict) -> dict:
    return {
        "ok": False,
        "routing": {
            "accepted": False,
            "blockedSteps": acceptance.get("blockedSteps") or [],
            "violations": acceptance.get("violations") or [],
            "steps": _routing_steps(acceptance),
        },
        "results": {},
        "twin_inventory": inventory,
    }


def _needs_selection_envelope(selection: dict, acceptance: dict, inventory: dict) -> dict:
    return {
        "ok": False,
        "needsSelection": selection.get("needsSelection") or {},
        "routing": {
            "accepted": True,
            "blockedSteps": [],
            "violations": [],
            "steps": _routing_steps(acceptance),
        },
        "results": {},
        "twin_inventory": inventory,
    }


def _result_envelope(flow: dict, env: dict, acceptance: dict, inventory: dict) -> dict:
    capture_step, capture = _resolve_capture_result(flow, env)
    envelope = {
        "ok": bool(capture_step and capture and not capture.get("kind")),
        "routing": {
            "accepted": bool(acceptance.get("accepted")),
            "blockedSteps": [],
            "violations": acceptance.get("violations") or [],
            "steps": _routing_steps(acceptance),
        },
        "results": {},
        "twin_inventory": inventory,
        "flow": flow,
    }
    if capture and not capture.get("kind"):
        envelope["results"]["capture"] = {
            "ok": True,
            "invokedUri": "kvm://host/screen/query/capture",
            "result": {
                "kind": "screenshot",
                "monitor": capture.get("monitor"),
                "scope": capture.get("scope", "monitor"),
                "source": capture.get("source"),
            },
        }
    return envelope


def _planner_error_envelope(error: Exception, inventory: dict) -> dict:
    return {
        "ok": False,
        "error": f"{type(error).__name__}: {error}",
        "routing": {
            "accepted": False,
            "blockedSteps": [{"reason": "planner-error"}],
            "violations": ["planner-error"],
            "steps": [],
        },
        "results": {},
        "twin_inventory": inventory,
    }


def run_real(case: dict, *, use_llm: bool = False):
    """Seam: run one case against the installed urirun planner + router accept.

    This is intentionally non-destructive: it runs the real planner, the real
    env-enum resolver and the real router acceptance predicate, then simulates
    the final screenshot result from the controlled Twin fixture.
    """
    _ensure_real_paths()
    from urirun_flow.env_selection import resolve_env_enums  # noqa: PLC0415
    from urirun_flow.flow_planner import make_flow  # noqa: PLC0415
    from urirun_connector_router.routing import accept_plan  # noqa: PLC0415

    env = sim.make_env(**case["env_spec"])
    inventory = sim._inventory_block(env)
    routes = _real_routes()
    mesh = {
        "nodes": [{"name": "host"}],
        "routes": routes,
        "inventories": {"host": inventory},
    }
    try:
        flow, generator = make_flow(
            case["intent"],
            mesh,
            selected_nodes=["host"],
            use_llm=use_llm,
            environments=_planner_environments(env, inventory),
        )
    except Exception as exc:  # noqa: BLE001
        return _planner_error_envelope(exc, inventory), env
    selection = resolve_env_enums(flow, routes, {"host": inventory}, memory=_Memory(env))
    flow_for_accept = selection.get("flow") if isinstance(selection.get("flow"), dict) else flow
    acceptance = accept_plan(flow_for_accept.get("steps") or [], mesh, probe=False)
    if selection.get("kind") == "needs-selection":
        return _needs_selection_envelope(selection, acceptance, inventory), env
    if selection.get("kind") == "env-domain-invalid":
        acceptance = {
            **acceptance,
            "accepted": False,
            "violations": [selection.get("violation") or selection.get("kind")],
        }
    if not acceptance.get("accepted"):
        return _reject_envelope(acceptance, inventory), env
    envelope = _result_envelope(flow_for_accept, env, acceptance, inventory)
    envelope["generator"] = generator
    return envelope, env


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true", help="print NL lines only")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--real", action="store_true", help="run against installed urirun")
    ap.add_argument("--llm", action="store_true", help="with --real, use the LLM planner")
    ap.add_argument("--mr", default=None, help="filter to one metamorphic family tag")
    args = ap.parse_args(argv)

    cases = transforms.expand()
    if args.mr:
        cases = [c for c in cases if args.mr in c["mr"]]

    if args.list:
        for c in cases:
            print(f"{c['id']:24s} [{c['mr']:18s}] {c['intent']}")
        print(f"\n# {len(cases)} NL cases", file=sys.stderr)
        return 0

    def executor(case: dict):
        return run_real(case, use_llm=args.llm) if args.real else sim.run_case_reference(case)
    results, passed = [], 0
    for c in cases:
        try:
            envelope, env_state = executor(c)
            viol = properties.check(c, env_state, envelope)
        except NotImplementedError as e:
            print(str(e), file=sys.stderr)
            return 2
        ok = not viol
        passed += ok
        results.append({"id": c["id"], "mr": c["mr"], "intent": c["intent"],
                        "expect": c["expect"]["kind"], "ok": ok, "violations": viol})

    if args.json:
        print(json.dumps({"total": len(cases), "passed": passed, "cases": results}, indent=2))
        return 0 if passed == len(cases) else 1

    by_mr: dict[str, list[int]] = {}
    for r in results:
        agg = by_mr.setdefault(r["mr"], [0, 0])
        agg[0] += r["ok"]
        agg[1] += 1
    for r in results:
        if not r["ok"]:
            print(f"✗ {r['id']:24s} {r['intent']}")
            for x in r["violations"]:
                print(f"      - {x}")
    print("\nMetamorphic family               pass/total")
    for mr, (p, t) in sorted(by_mr.items()):
        mark = "✓" if p == t else "✗"
        print(f"  {mark} {mr:30s} {p}/{t}")
    print(f"\nRESULT: {passed}/{len(cases)} NL cases satisfy all invariants")
    return 0 if passed == len(cases) else 1


if __name__ == "__main__":
    raise SystemExit(main())
