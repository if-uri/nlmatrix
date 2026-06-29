#!/usr/bin/env python3
"""Gen 5 — żywy harness (HTTP), ten sam checker co offline.

Czyta REALNY mesh z `/api/objects` (live: env czytany z odpowiedzi, nie
hardkodowany), framuje tę samą operację (`zrob zrzut ekranu`) po każdym
dostępnym targecie i sprawdza routing **tym samym** `gen5_cross_target.check`,
którym offline łapiemy mutanta "wszystko → host".

Read-only: `execute=False` → tylko plan/routing, zero efektów ubocznych.
Skok przez planner-error/HTTP-error jako infra-skip (nie green-washujemy outage).

Uruchom (dashboard na :8194):  python3 gen5_live.py
"""
from __future__ import annotations

import argparse
import http.client
import json
import sys
import urllib.error
import urllib.request

import gen5_cross_target as g5

BASE = "http://127.0.0.1:8194"


def _get(path: str, timeout: float) -> dict:
    with urllib.request.urlopen(BASE + path, timeout=timeout) as r:
        return json.loads(r.read())


def _post_chat(targets: list[str], timeout: float) -> dict:
    body = {"prompt": "zrob zrzut ekranu", "targets": targets, "execute": False,
            "target_explicit": True, "action": "chat:run", "no_llm": True}
    req = urllib.request.Request(BASE + "/api/chat/ask", data=json.dumps(body).encode(),
                                 method="POST", headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def live_result(env: dict) -> dict:
    """Map the live chat envelope onto the Gen-5 result shape the checker expects.

    Gen 5 is about TARGET routing, which lives in selectedNodes/selectedTargets —
    present even when the step itself needs a monitor selection (that env-enum
    ambiguity is Gen 9, orthogonal). So routing is read from the resolved targets,
    not from `ok`: an unreachable target resolves to NO target (blocked), never host."""
    nodes = env.get("selectedNodes") or []
    tgts = env.get("selectedTargets") or []
    if nodes:
        return {"status": "ok", "runsOn": nodes[0], "reason": "node-selected"}
    if tgts == ["host"]:
        return {"status": "ok", "runsOn": "host", "reason": "host-default"}
    return {"status": "blocked", "runsOn": None, "reason": "unreachable"}


def cases_from_mesh(objects: list[dict]) -> list[dict]:
    """Build a Gen-5 case per live target, with expectation derived from reachability.

    Expectations omit `reason` (live wording differs); status/runsOn + the teeth
    (explicit_node/node_reachable/unreachable) are what the shared checker enforces."""
    cases = []
    for obj in objects:
        tid = str(obj.get("id") or "")
        reachable = bool(obj.get("reachable"))
        if tid == "host":
            cases.append({"id": "host", "target": ["host"],
                          "expect": {"status": "ok", "runsOn": "host"}})
        elif tid.startswith("node:"):
            name = tid.split(":", 1)[1]
            if reachable:
                cases.append({"id": tid, "target": [tid], "explicit_node": name, "node_reachable": True,
                              "expect": {"status": "ok", "runsOn": name}})
            else:
                cases.append({"id": tid, "target": [tid], "unreachable": True,
                              "expect": {"status": "blocked", "runsOn": None}})
        # services have their own lifecycle semantics (running/stopped) outside the
        # host↔node compute-routing dimension Gen 5 covers — skipped here.
    # the regression shape: host + explicit reachable node, explicit must win
    reach_node = next((o for o in objects if str(o.get("id","")).startswith("node:") and o.get("reachable")), None)
    if reach_node:
        name = reach_node["id"].split(":", 1)[1]
        cases.append({"id": f"host+{reach_node['id']}", "target": ["host", reach_node["id"]],
                      "explicit_node": name, "node_reachable": True,
                      "expect": {"status": "ok", "runsOn": name}})
    return cases


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--timeout", type=float, default=60.0)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    try:
        objects = (_get("/api/objects", args.timeout) or {}).get("objects") or []
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        print(f"dashboard unreachable at {BASE}: {e}", file=sys.stderr)
        return 2

    cases = cases_from_mesh(objects)
    passed = skipped = 0
    results = []
    for c in cases:
        try:
            env = _post_chat(c["target"], args.timeout)
        except (urllib.error.URLError, urllib.error.HTTPError, http.client.RemoteDisconnected,
                TimeoutError, ValueError) as e:
            skipped += 1
            results.append({"id": c["id"], "skipped": str(e)})
            print(f"⊘ {c['id']:24s} HTTP/parse skip: {e}")
            continue
        # a planner outage is an infra skip, not a passing reject
        if env.get("kind") == "planner-error" or (env.get("error") and not env.get("flow")):
            skipped += 1
            results.append({"id": c["id"], "skipped": "planner-error"})
            print(f"⊘ {c['id']:24s} planner-error (infra skip)")
            continue
        res = live_result(env)
        viol = g5.check(c, res)
        ok = not viol
        passed += ok
        results.append({"id": c["id"], "result": res, "violations": viol})
        print(f"{'✓' if ok else '✗'} {c['id']:24s} status={res['status']:8s} runsOn={str(res['runsOn']):14s}")
        for x in viol:
            print(f"      - {x}")
    checked = len(cases) - skipped
    if args.json:
        print(json.dumps({"passed": passed, "checked": checked, "skipped": skipped, "results": results}, indent=2))
    print(f"\nRESULT: {passed}/{checked} live cross-target cases honest "
          f"({skipped} infra-skip) — same checker as offline Gen 5")
    return 0 if checked and passed == checked else 1


if __name__ == "__main__":
    raise SystemExit(main())
