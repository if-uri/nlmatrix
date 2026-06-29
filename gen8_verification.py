"""Gen 8 — uczciwość weryfikacji.

Obala błędną architekturę: "`ok:true` na kroku == zadanie zrobione". Wadliwa
architektura ufa transportowemu `ok` i melduje "done", choć stan świata się nie
zmienił (phantom-success), a przy awarii kroku cicho się zatrzymuje bez recovery.

Honorowy silnik wykonuje flow, po czym uruchamia `verify(state)` na realnym
świecie — "done" tylko gdy stan faktycznie spełnia cel. Niezmienniki z zębami:
  - `verify(state)` False ⟹ wynik NIE "done" (phantom złapany);
  - awaria kroku → recovery (nextIntent), nie cichy stop.

Uruchom:  python3 gen8_verification.py
Testy:    python3 -m pytest test_gen8.py -q

Hak urirun: contracts.flow_execution_verification,
decision_loop.general_path_next_intent, urifix_bridge.try_urifix_repair.
"""
from __future__ import annotations


def _new_world() -> dict:
    return {"files": set()}


def _write(path):
    def apply(w):
        w["files"].add(path)
    return apply


def execute(flow: dict) -> dict:
    """Honest: run the steps, then VERIFY the world. `ok:true` alone is not 'done'."""
    world = _new_world()
    for step in flow["steps"]:
        if not step["ok"]:
            return {"status": "failed", "step": step["id"], "verified": None, "world": world,
                    "recovery": [{"step": step["id"], "nextIntent": "diagnose-and-retry"}]}
        if step.get("apply"):
            step["apply"](world)
        # a phantom step reports ok:true but carries no apply → no real effect
    verified = flow["verify"](world)
    return {"status": "done" if verified else "not-done", "verified": verified,
            "world": world, "recovery": []}


def buggy_execute(flow: dict) -> dict:
    """The flawed architecture: `ok:true` on every step == done. Never checks the
    world. A phantom step passes; a failure stops silently with no recovery."""
    world = _new_world()
    for step in flow["steps"]:
        if not step["ok"]:
            return {"status": "not-done", "step": step["id"], "verified": None,
                    "world": world, "recovery": []}  # silent stop
        if step.get("apply"):
            step["apply"](world)
    return {"status": "done", "verified": None, "world": world, "recovery": []}


# --- ziarno + transformacje --------------------------------------------------
def _verify_out(w):
    return "/out.txt" in w["files"]


def expand() -> list[dict]:
    write_out = {"id": "write", "ok": True, "apply": _write("/out.txt")}
    phantom = {"id": "phantom-write", "ok": True, "apply": None}          # claims success, does nothing
    write_other = {"id": "write-other", "ok": True, "apply": _write("/elsewhere.txt")}
    fail = {"id": "broken", "ok": False, "apply": None}
    return [
        {"id": "clean-done", "flow": {"steps": [write_out], "verify": _verify_out},
         "expect": {"status": "done"}},
        {"id": "phantom-success", "phantom": True, "flow": {"steps": [phantom], "verify": _verify_out},
         "expect": {"status": "not-done"}},
        {"id": "wrong-effect", "phantom": True, "flow": {"steps": [write_other], "verify": _verify_out},
         "expect": {"status": "not-done"}},
        {"id": "step-failure", "expect_failure": True, "flow": {"steps": [fail, write_out], "verify": _verify_out},
         "expect": {"status": "failed"}},
        {"id": "partial-then-phantom", "phantom": True,
         "flow": {"steps": [write_other, phantom], "verify": _verify_out},
         "expect": {"status": "not-done"}},
    ]


# --- niezmienniki (z zębami) --------------------------------------------------
def check(case: dict, result: dict) -> list[str]:
    v: list[str] = []
    exp = case["expect"]
    if result["status"] != exp["status"]:
        v.append(f"status: expected {exp['status']} got {result['status']}")
    # TEETH 1: if the real world fails verification, the result must NOT be 'done'
    actually = case["flow"]["verify"](result["world"])
    if result["status"] == "done" and not actually:
        v.append("phantom-success: reported done but verify(state) is False")
    # TEETH 2: a step failure must yield recovery (nextIntent), not a silent stop
    if case.get("expect_failure") and not result.get("recovery"):
        v.append("silent-stop: step failed with no recovery nextIntent")
    return v


def run_case(case: dict, engine=execute) -> dict:
    return engine(case["flow"])


def main() -> int:
    cases = expand()
    passed = 0
    for c in cases:
        res = run_case(c)
        viol = check(c, res)
        ok = not viol
        passed += ok
        print(f"{'✓' if ok else '✗'} {c['id']:22s} status={res['status']:9s} verified={res.get('verified')}")
        for x in viol:
            print(f"      - {x}")
    print(f"\nRESULT: {passed}/{len(cases)} verification-honesty cases satisfy all invariants")
    return 0 if passed == len(cases) else 1


if __name__ == "__main__":
    raise SystemExit(main())
