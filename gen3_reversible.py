"""Gen 3 — odwracalność / rollback.

Obala błędną architekturę: "`reversible` to etykieta, nie zdolność; system ufa
fladze". Twój żywy ślad oznacza KAŻDY krok `reversible:true`, nigdy tego nie
weryfikując. Ta generacja wykonuje mutujące flow na małym świecie, buduje ledger
inwersji i sprawia, że na częściowej awarii świat wraca do stanu początkowego —
a krok, który deklaruje odwracalność bez inverse (kłamstwo), jest wykrywany.

Uruchom:  python3 gen3_reversible.py
Testy:    python3 -m pytest test_gen3.py -q
"""
from __future__ import annotations

from typing import Any


# --- świat (mutowalny stan) ---------------------------------------------------
class World:
    def __init__(self, windows, files):
        self.windows = set(windows)
        self.files = dict(files)

    def copy(self) -> "World":
        return World(self.windows, self.files)

    def snapshot(self):
        return (frozenset(self.windows), tuple(sorted(self.files.items())))


# --- operacje: forward + obliczona inwersja -----------------------------------
def _close(world: World, p: dict) -> dict:
    wid = p["window"]
    world.windows.discard(wid)
    return {"uri": "win://host/window/command/open", "payload": {"window": wid}}


def _open(world: World, p: dict) -> dict:
    wid = p["window"]
    world.windows.add(wid)
    return {"uri": "win://host/window/command/close", "payload": {"window": wid}}


def _write(world: World, p: dict) -> dict:
    path, content = p["path"], p["content"]
    prior = world.files.get(path)
    world.files[path] = content
    if prior is None:
        return {"uri": "fs://host/file/command/delete", "payload": {"path": path}}
    return {"uri": "fs://host/file/command/write", "payload": {"path": path, "content": prior}}


def _delete(world: World, p: dict) -> dict:
    path = p["path"]
    prior = world.files.pop(path, None)
    if prior is None:
        return {"noop": True}
    return {"uri": "fs://host/file/command/write", "payload": {"path": path, "content": prior}}


# registry: declared effect + reversibility + handler (None handler => no inverse)
REGISTRY: dict[str, dict] = {
    "win://host/window/command/close": {"effect": "command", "reversible": True, "apply": _close},
    "win://host/window/command/open": {"effect": "command", "reversible": True, "apply": _open},
    "fs://host/file/command/write": {"effect": "command", "reversible": True, "apply": _write},
    "fs://host/file/command/delete": {"effect": "command", "reversible": True, "apply": _delete},
    "win://host/window/query/list": {"effect": "query", "reversible": True, "apply": None},
    # nieodwracalna: e-mail wychodzi z systemu, brak inverse
    "mail://host/msg/command/send": {"effect": "command", "reversible": False, "apply": None},
    # KŁAMSTWO: deklaruje reversible:true, ale handler nie zwraca inwersji
    "ghost://host/x/command/poof": {"effect": "command", "reversible": True, "apply": lambda w, p: None},
}


def _rollback(ledger: list[dict], world: World) -> None:
    """Apply recorded inverses in REVERSE order — restore prior position."""
    for entry in reversed(ledger):
        inv = entry["inverse"]
        if not inv or inv.get("noop"):
            continue
        reg = REGISTRY.get(inv["uri"])
        if reg and reg.get("apply"):
            reg["apply"](world, inv["payload"])


def execute(flow: dict, world: World, fail_at: int | None = None, confirm: bool = False) -> dict:
    """Honest ReversibleProcess: accept-then-execute, ledger inverses, rollback."""
    initial = world.copy()

    # ACCEPT phase: reject the plan up-front if it mutates irreversibly w/o confirm
    for step in flow["steps"]:
        reg = REGISTRY.get(step["uri"])
        if reg and reg["effect"] == "command" and not reg["reversible"] and not confirm:
            return {"status": "blocked", "ledger": [], "rolled_back": False,
                    "restored": None, "blocked": [{"uri": step["uri"],
                    "reason": "non-reversible-needs-confirm"}], "world": world,
                    "initial": initial.snapshot()}

    ledger: list[dict] = []
    for i, step in enumerate(flow["steps"]):
        uri = step["uri"]
        reg = REGISTRY.get(uri)
        if reg is None:
            _rollback(ledger, world)
            return {"status": "blocked", "ledger": ledger, "rolled_back": True,
                    "restored": world.snapshot() == initial.snapshot(),
                    "blocked": [{"uri": uri, "reason": "no-route"}], "world": world,
                    "initial": initial.snapshot()}
        if reg["effect"] == "query":
            continue
        if fail_at is not None and i == fail_at:
            _rollback(ledger, world)
            return {"status": "failed", "ledger": ledger, "rolled_back": True,
                    "restored": world.snapshot() == initial.snapshot(),
                    "blocked": [], "world": world, "initial": initial.snapshot()}
        inverse = reg["apply"](world, step.get("payload", {})) if reg["apply"] else None
        # reversible declared, command, but no inverse produced => the lie
        if inverse is None:
            _rollback(ledger, world)
            return {"status": "lie-refused", "ledger": ledger, "rolled_back": True,
                    "restored": world.snapshot() == initial.snapshot(),
                    "blocked": [{"uri": uri, "reason": "reversible-without-inverse"}],
                    "world": world, "initial": initial.snapshot()}
        ledger.append({"forward": uri, "inverse": inverse})

    return {"status": "ok", "ledger": ledger, "rolled_back": False, "restored": None,
            "blocked": [], "world": world, "initial": initial.snapshot()}


def buggy_execute(flow: dict, world: World, fail_at: int | None = None, confirm: bool = False) -> dict:
    """The flawed architecture: trusts the `reversible` flag — records inverses
    without checking they exist, and does NOT roll back on failure."""
    initial = world.copy()
    ledger: list[dict] = []
    for i, step in enumerate(flow["steps"]):
        reg = REGISTRY.get(step["uri"])
        if not reg or reg["effect"] == "query":
            continue
        if fail_at is not None and i == fail_at:
            return {"status": "failed", "ledger": ledger, "rolled_back": False,
                    "restored": world.snapshot() == initial.snapshot(), "blocked": [],
                    "world": world, "initial": initial.snapshot()}
        inverse = reg["apply"](world, step.get("payload", {})) if reg["apply"] else None
        ledger.append({"forward": step["uri"], "inverse": inverse})  # no lie-check
    return {"status": "ok", "ledger": ledger, "rolled_back": False, "restored": None,
            "blocked": [], "world": world, "initial": initial.snapshot()}


# --- seed + metamorphic transforms -------------------------------------------
INITIAL = {"windows": ["w1", "w2"], "files": {"/tmp/a": "old"}}


def _flow(*steps):
    return {"steps": list(steps)}


def expand() -> list[dict]:
    C = "win://host/window/command/close"
    W = "fs://host/file/command/write"
    POOF = "ghost://host/x/command/poof"
    SEND = "mail://host/msg/command/send"
    cases = []
    for win, path in (("w1", "/tmp/a"), ("w2", "/tmp/b")):
        close = {"uri": C, "payload": {"window": win}}
        write = {"uri": W, "payload": {"path": path, "content": "X"}}
        poof = {"uri": POOF, "payload": {}}
        send = {"uri": SEND, "payload": {"to": "x@y"}}
        cases += [
            {"id": f"clean-{win}", "flow": _flow(close, write), "fail_at": None,
             "expect": {"status": "ok"}},
            {"id": f"fail-mid-{win}", "flow": _flow(close, write), "fail_at": 1,
             "expect": {"status": "failed"}},
            {"id": f"fail-first-{win}", "flow": _flow(close, write), "fail_at": 0,
             "expect": {"status": "failed"}},
            {"id": f"lie-first-{win}", "flow": _flow(poof, write), "fail_at": None,
             "expect": {"status": "lie-refused"}},
            {"id": f"lie-second-{win}", "flow": _flow(close, poof), "fail_at": None,
             "expect": {"status": "lie-refused"}},
            {"id": f"nonrev-{win}", "flow": _flow(close, send), "fail_at": None,
             "expect": {"status": "blocked", "blocked_reason": "non-reversible-needs-confirm"}},
        ]
    return cases


# --- invariants ---------------------------------------------------------------
def check(case: dict, result: dict) -> list[str]:
    v: list[str] = []
    exp = case["expect"]
    if result["status"] != exp["status"]:
        v.append(f"status: expected {exp['status']} got {result['status']}")
    # every executed command in the ledger carries an inverse (no lie slipped)
    for e in result["ledger"]:
        if e["inverse"] is None:
            v.append(f"reversibility-lie: {e['forward']} executed with no inverse")
    # any non-terminal failure must roll back, restoring the world
    if result["status"] in ("failed", "lie-refused", "blocked") and result.get("rolled_back"):
        if result.get("restored") is not True:
            v.append("rollback: world NOT restored to initial after rollback")
    # failure/lie must actually roll back (the flawed engine leaves residue)
    if result["status"] in ("failed", "lie-refused") and not result.get("rolled_back"):
        v.append("recovery: failure left the world mutated (no rollback)")
    # non-reversible must be gated up-front
    if exp.get("blocked_reason"):
        reasons = [b["reason"] for b in result.get("blocked", [])]
        if exp["blocked_reason"] not in reasons:
            v.append(f"gating: expected blocked {exp['blocked_reason']}, got {reasons}")
    return v


def run_case(case: dict, engine=execute) -> dict:
    world = World(**INITIAL)
    return engine(case["flow"], world, fail_at=case["fail_at"])


def main() -> int:
    cases = expand()
    passed = 0
    for c in cases:
        res = run_case(c)
        viol = check(c, res)
        ok = not viol
        passed += ok
        mark = "✓" if ok else "✗"
        restored = "" if res.get("restored") is None else f" restored={res['restored']}"
        print(f"{mark} {c['id']:16s} status={res['status']:12s} ledger={len(res['ledger'])}{restored}")
        for x in viol:
            print(f"      - {x}")
    print(f"\nRESULT: {passed}/{len(cases)} reversibility cases satisfy all invariants")
    return 0 if passed == len(cases) else 1


if __name__ == "__main__":
    raise SystemExit(main())
