"""Gen 5 — cross-target routing.

Obala błędną architekturę: "wszystko po cichu spada na host". Router, który
ignoruje jawny wybór targetu i routuje wszystko na host (albo cicho fallbackuje
nieosiągalny target na host zamiast blokować), wygląda na działający dopóki nie
poprosisz o `node:lenovo` lub usługę — wtedy po cichu robi to gdzie indziej.

To dokładnie regresja złapana w tej sesji: refaktor usunął guard
`if not _has_explicit_remote_selection(...)` wokół `_apply_host_default_*`, więc
`targets=["host","node:lenovo"]` lądowało na host (`selectedNodes=[]`). Ta
generacja koduje tę klasę jako niezmiennik z zębami: honorowy router przechodzi,
silnik-mutant "everything → host" jest łapany tym samym checkerem.

Niezmienniki:
  - `runsOn` zgodny z nazwanym/wywnioskowanym targetem;
  - jawny wybór node wygrywa z host-defaultem z tekstu promptu;
  - nieosiągalny target → typed block, NIE cichy fallback na host;
  - usługa zatrzymana → block, nie host.

Uruchom:  python3 gen5_cross_target.py
Testy:    python3 -m pytest test_gen5.py -q

Hak urirun: discovery.discover_mesh, _route_targets_active, _apply_host_default_*,
node_dispatch.run_node_uri, routing.runsOnByStep.
"""
from __future__ import annotations


# --- świat: stan meshu (osiągalność node/usług) ------------------------------
class Mesh:
    def __init__(self, nodes=None, services=None):
        self.nodes = dict(nodes or {})        # name -> reachable(bool)
        self.services = dict(services or {})  # name -> running(bool)

    def node_reachable(self, name: str) -> bool:
        return bool(self.nodes.get(name))

    def service_running(self, name: str) -> bool:
        return bool(self.services.get(name))


# --- jaki target wskazuje żądanie (przed sprawdzeniem osiągalności) ----------
def _selected_target(intent: dict, mesh: Mesh):
    """The target the request DESIGNATES. Explicit UI/API node/service selection
    wins; otherwise a node named in the prompt; otherwise host (default)."""
    if intent.get("target_explicit"):
        for t in intent.get("targets") or []:
            if t.startswith("node:") and t[5:]:
                return ("node", t[5:])
            if t.startswith("service:") and t[8:]:
                return ("service", t[8:])
        for n in intent.get("nodes") or []:
            if n:
                return ("node", str(n))
    prompt_words = (intent.get("prompt") or "").lower().split()
    named = [n for n in mesh.nodes if n in prompt_words]
    if len(named) > 1:
        return ("ambiguous", ",".join(sorted(named)))
    if named:
        return ("node", named[0])
    return ("host", "host")


# --- honorowy router: funkcja (intent, mesh) -> decyzja ----------------------
def route(intent: dict, mesh: Mesh) -> dict:
    kind, name = _selected_target(intent, mesh)
    if kind == "host":
        return {"status": "ok", "runsOn": "host", "reason": "host-default"}
    if kind == "ambiguous":
        return {"status": "blocked", "runsOn": None, "reason": "ambiguous-target"}
    if kind == "service":
        if mesh.service_running(name):
            return {"status": "ok", "runsOn": f"service:{name}", "reason": "service-selected"}
        return {"status": "blocked", "runsOn": None, "reason": "service-stopped"}
    # node
    if mesh.node_reachable(name):
        return {"status": "ok", "runsOn": name, "reason": "node-selected"}
    return {"status": "blocked", "runsOn": None, "reason": "unreachable-node"}


def buggy_route(intent: dict, mesh: Mesh) -> dict:
    """The flawed architecture: every request silently runs on host. Explicit
    node/service selections are dropped; unreachable targets are not blocked —
    they just quietly execute somewhere else (host). This is the regression."""
    return {"status": "ok", "runsOn": "host", "reason": "host-default"}


# --- ziarno + transformacje metamorficzne ------------------------------------
MESH = Mesh(
    nodes={"lenovo": True, "offline": False, "lab-1": True, "lab-2": True},
    services={"scanner": True, "deadsvc": False},
)


def expand() -> list[dict]:
    """One base operation ("zrob zrzut"), reframed across targets. Each transform
    has a predictable effect on the expected runsOn / status."""
    return [
        {"id": "explicit-node-reachable", "explicit_node": "lenovo", "node_reachable": True,
         "intent": {"prompt": "zrob zrzut", "targets": ["node:lenovo"], "target_explicit": True},
         "expect": {"status": "ok", "runsOn": "lenovo", "reason": "node-selected"}},
        {"id": "explicit-node-offline", "unreachable": True,
         "intent": {"prompt": "zrob zrzut", "targets": ["node:offline"], "target_explicit": True},
         "expect": {"status": "blocked", "runsOn": None, "reason": "unreachable-node"}},
        {"id": "host-default-no-node",
         "intent": {"prompt": "zrob zrzut", "targets": [], "target_explicit": True},
         "expect": {"status": "ok", "runsOn": "host", "reason": "host-default"}},
        {"id": "prompt-names-node",
         "intent": {"prompt": "sprawdz health na lenovo", "targets": [], "target_explicit": False},
         "expect": {"status": "ok", "runsOn": "lenovo", "reason": "node-selected"}},
        # THE regression case: explicit node + benign prompt that names no node.
        {"id": "explicit-wins-benign-prompt", "explicit_node": "lenovo", "node_reachable": True,
         "intent": {"prompt": "ogarnij to", "targets": ["node:lenovo"], "target_explicit": True},
         "expect": {"status": "ok", "runsOn": "lenovo", "reason": "node-selected"}},
        # mixed host+node (the test_chat_ask_derives_nodes_from_node_targets shape).
        {"id": "mixed-host-and-node", "explicit_node": "lenovo", "node_reachable": True,
         "intent": {"prompt": "sprawdz health", "targets": ["host", "node:lenovo"], "target_explicit": True},
         "expect": {"status": "ok", "runsOn": "lenovo", "reason": "node-selected"}},
        {"id": "service-running",
         "intent": {"prompt": "skanuj", "targets": ["service:scanner"], "target_explicit": True},
         "expect": {"status": "ok", "runsOn": "service:scanner", "reason": "service-selected"}},
        {"id": "service-stopped",
         "intent": {"prompt": "skanuj", "targets": ["service:deadsvc"], "target_explicit": True},
         "expect": {"status": "blocked", "runsOn": None, "reason": "service-stopped"}},
        {"id": "ambiguous-alias",
         "intent": {"prompt": "porownaj lab-1 lab-2", "targets": [], "target_explicit": False},
         "expect": {"status": "blocked", "runsOn": None, "reason": "ambiguous-target"}},
    ]


# --- niezmienniki (z zębami) --------------------------------------------------
def check(case: dict, result: dict) -> list[str]:
    v: list[str] = []
    exp = case["expect"]
    if result["status"] != exp["status"]:
        v.append(f"status: expected {exp['status']} got {result['status']}")
    if "runsOn" in exp and result.get("runsOn") != exp["runsOn"]:
        v.append(f"runsOn: expected {exp['runsOn']} got {result.get('runsOn')}")
    if exp.get("reason") and result.get("reason") != exp["reason"]:
        v.append(f"reason: expected {exp['reason']} got {result.get('reason')}")
    # TEETH 1: an explicit, reachable node selection must NOT be silently rerouted to host.
    if case.get("explicit_node") and case.get("node_reachable"):
        if result.get("runsOn") != case["explicit_node"]:
            v.append(f"silent-host-fallback: explicit node '{case['explicit_node']}' "
                     f"routed to '{result.get('runsOn')}'")
    # TEETH 2: an unreachable target must be a typed block, never a quiet host fallback.
    if case.get("unreachable"):
        if not (result["status"] == "blocked" and result.get("runsOn") is None):
            v.append(f"unreachable-not-blocked: unreachable target ran on "
                     f"'{result.get('runsOn')}' (status={result['status']})")
    return v


def run_case(case: dict, engine=route) -> dict:
    return engine(case["intent"], MESH)


def main() -> int:
    cases = expand()
    passed = 0
    for c in cases:
        res = run_case(c)
        viol = check(c, res)
        ok = not viol
        passed += ok
        mark = "✓" if ok else "✗"
        print(f"{mark} {c['id']:26s} status={res['status']:8s} runsOn={str(res.get('runsOn')):14s}")
        for x in viol:
            print(f"      - {x}")
    print(f"\nRESULT: {passed}/{len(cases)} cross-target cases satisfy all invariants")
    return 0 if passed == len(cases) else 1


if __name__ == "__main__":
    raise SystemExit(main())
