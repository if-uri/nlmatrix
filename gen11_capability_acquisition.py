"""Gen 11 - capability gap + runtime self-extension.

This is the first generation where the robot does not only execute inside a
fixed action space. It encounters a missing capability, acquires/generates the
missing connector at runtime, admits the generated contract through the same
gate as hand-written contracts, and resumes from the blocked step.

The invariant: self-extension is not a gate bypass. Acquisition is soft;
admission is hard.

Run:   python3 gen11_capability_acquisition.py
Tests: python3 -m pytest test_gen11.py -q
"""
from __future__ import annotations

from typing import Any


class World:
    def __init__(self):
        self.installed_schemes: set[str] = set()
        self.installed_apps: set[str] = set()
        self.files: dict[str, Any] = {}
        self.raster: bytes | None = None
        self.acquirable_schemes: set[str] = set()
        self.acquirable_apps: set[str] = set()
        self.scheme_deps: dict[str, str] = {}
        self.providers: dict[str, dict] = {}


def _read(_world: World, _payload: dict) -> None:
    return None


def _rasterize(world: World, _payload: dict) -> None:
    world.raster = b"PNGDATA"


def _write(world: World, payload: dict) -> dict:
    out = payload["out"]
    prior = world.files.get(out)
    world.files[out] = world.raster
    if prior is None:
        return {"uri": "fs://host/file/command/delete", "payload": {"path": out}}
    return {"uri": "fs://host/file/command/write", "payload": {"path": out, "content": prior}}


FS_READ = {
    "uri": "fs://host/file/query/read",
    "declared": {"effect": "query", "reversible": False, "inverse": None},
    "apply": _read,
}
FS_WRITE = {
    "uri": "fs://host/file/command/write",
    "declared": {
        "effect": "command",
        "reversible": True,
        "inverse": "fs://host/file/command/delete",
    },
    "apply": _write,
}

IMG_HONEST = {
    "uri": "img://host/svg/command/rasterize",
    "declared": {"effect": "query", "reversible": False, "inverse": None},
    "apply": _rasterize,
}
IMG_LYING = {
    "uri": "img://host/svg/command/rasterize",
    "declared": {"effect": "command", "reversible": True, "inverse": None},
    "apply": _rasterize,
}


def _base_registry() -> dict:
    return {FS_READ["uri"]: FS_READ, FS_WRITE["uri"]: FS_WRITE}


def _scheme(uri: str) -> str:
    return uri.split("://", 1)[0]


def admit(declared: dict) -> list[str]:
    """Admission gate for generated contracts."""
    violations: list[str] = []
    if declared.get("effect") not in ("query", "command"):
        violations.append("bad-effect")
    if declared.get("effect") == "command" and declared.get("reversible") and not declared.get("inverse"):
        violations.append("reversible-without-inverse")
    return violations


def _need(scheme: str | None, app: str | None, recoverable: bool) -> dict:
    return {"kind": "need", "scheme": scheme, "app": app, "recoverable": recoverable}


def _acquire_scheme(world: World, scheme: str, registry: dict, acquired_log: list) -> dict | None:
    """Acquire a missing scheme and admit the generated connector contract."""
    dep_app = world.scheme_deps.get(scheme)
    if dep_app and dep_app not in world.installed_apps:
        if dep_app not in world.acquirable_apps:
            return _need(scheme, dep_app, recoverable=False)
        world.installed_apps.add(dep_app)
    if scheme not in world.acquirable_schemes:
        return _need(scheme, None, recoverable=False)
    entry = world.providers[scheme]
    violations = admit(entry["declared"])
    acquired_log.append({"uri": entry["uri"], "admitted": not violations, "violations": violations})
    if violations:
        return {"kind": "gate-rejected", "uri": entry["uri"], "violations": violations}
    registry[entry["uri"]] = entry
    world.installed_schemes.add(scheme)
    return None


def run_episode(goal: dict, world: World, prior_ledger: list[str] | None = None) -> dict:
    done = list(prior_ledger or [])
    registry = _base_registry()
    for scheme in world.installed_schemes:
        if scheme in world.providers:
            registry[world.providers[scheme]["uri"]] = world.providers[scheme]
    acquired: list[dict] = []
    re_executed: list[str] = []
    executed: list[str] = []

    for step in goal["steps"]:
        sid = step["id"]
        if sid in done:
            continue
        scheme = _scheme(step["uri"])
        if scheme not in world.installed_schemes:
            outcome = _acquire_scheme(world, scheme, registry, acquired)
            if outcome and outcome["kind"] == "need":
                return _blocked("blocked-need", outcome, acquired, executed, re_executed, goal, world)
            if outcome and outcome["kind"] == "gate-rejected":
                return _blocked("blocked-gate", outcome, acquired, executed, re_executed, goal, world)
        entry = registry[step["uri"]]
        if sid in done:
            re_executed.append(sid)
        entry["apply"](world, step.get("payload", {}))
        executed.append(sid)
        done.append(sid)

    verified = _verify(goal, world)
    return {
        "status": "ok" if verified else "unverified",
        "block": None,
        "acquired": acquired,
        "executed": executed,
        "re_executed": re_executed,
        "verified": verified,
    }


def _blocked(status: str, block: dict, acquired: list, executed: list,
             re_executed: list, goal: dict, world: World) -> dict:
    return {
        "status": status,
        "block": block,
        "acquired": acquired,
        "executed": executed,
        "re_executed": re_executed,
        "verified": _verify(goal, world),
    }


def _verify(goal: dict, world: World) -> bool:
    return bool(world.files.get(goal["output"]))


def buggy_skip_missing(goal: dict, world: World, prior_ledger: list[str] | None = None) -> dict:
    """Missing capability is silently marked as complete."""
    done = list(prior_ledger or [])
    registry = _base_registry()
    for scheme in world.installed_schemes:
        if scheme in world.providers:
            registry[world.providers[scheme]["uri"]] = world.providers[scheme]
    executed: list[str] = []
    for step in goal["steps"]:
        if step["id"] in done:
            continue
        scheme = _scheme(step["uri"])
        if scheme not in world.installed_schemes:
            done.append(step["id"])
            continue
        registry[step["uri"]]["apply"](world, step.get("payload", {}))
        executed.append(step["id"])
        done.append(step["id"])
    return {
        "status": "ok",
        "block": None,
        "acquired": [],
        "executed": executed,
        "re_executed": [],
        "verified": _verify(goal, world),
    }


def buggy_ungated_acquire(goal: dict, world: World, prior_ledger: list[str] | None = None) -> dict:
    """Generated connector is installed and used without enforcing admission."""
    done = list(prior_ledger or [])
    registry = _base_registry()
    for scheme in world.installed_schemes:
        if scheme in world.providers:
            registry[world.providers[scheme]["uri"]] = world.providers[scheme]
    acquired: list[dict] = []
    executed: list[str] = []
    for step in goal["steps"]:
        if step["id"] in done:
            continue
        scheme = _scheme(step["uri"])
        if scheme not in world.installed_schemes:
            dep = world.scheme_deps.get(scheme)
            if dep:
                world.installed_apps.add(dep)
            entry = world.providers[scheme]
            acquired.append({
                "uri": entry["uri"],
                "admitted": False,
                "violations": admit(entry["declared"]),
            })
            registry[entry["uri"]] = entry
            world.installed_schemes.add(scheme)
        registry[step["uri"]]["apply"](world, step.get("payload", {}))
        executed.append(step["id"])
        done.append(step["id"])
    return {
        "status": "ok",
        "block": None,
        "acquired": acquired,
        "executed": executed,
        "re_executed": [],
        "verified": _verify(goal, world),
    }


def buggy_restart(goal: dict, world: World, prior_ledger: list[str] | None = None) -> dict:
    """Recovery restarts the whole flow instead of resuming."""
    done = list(prior_ledger or [])
    registry = _base_registry()
    for scheme in world.installed_schemes:
        if scheme in world.providers:
            registry[world.providers[scheme]["uri"]] = world.providers[scheme]
    re_executed: list[str] = []
    executed: list[str] = []
    for step in goal["steps"]:
        if step["id"] in done:
            re_executed.append(step["id"])
        registry[step["uri"]]["apply"](world, step.get("payload", {}))
        executed.append(step["id"])
    return {
        "status": "ok",
        "block": None,
        "acquired": [],
        "executed": executed,
        "re_executed": re_executed,
        "verified": _verify(goal, world),
    }


GOAL = {
    "id": "export_diagram",
    "output": "/tmp/diagram.png",
    "steps": [
        {"id": "read_src", "uri": "fs://host/file/query/read", "payload": {"path": "/tmp/diagram.svg"}},
        {"id": "rasterize", "uri": "img://host/svg/command/rasterize", "payload": {}},
        {"id": "write_png", "uri": "fs://host/file/command/write", "payload": {"out": "/tmp/diagram.png"}},
    ],
}


def _world(installed_schemes, installed_apps=(), acquirable_schemes=(), acquirable_apps=(),
           provider=IMG_HONEST, raster=None, files=None) -> World:
    world = World()
    world.installed_schemes = set(installed_schemes)
    world.installed_apps = set(installed_apps)
    world.acquirable_schemes = set(acquirable_schemes)
    world.acquirable_apps = set(acquirable_apps)
    world.scheme_deps = {"img": "inkscape"}
    world.providers = {"img": provider}
    world.raster = raster
    world.files = dict(files or {})
    return world


def expand() -> list[dict]:
    return [
        {
            "id": "all-available",
            "prior": [],
            "world": lambda: _world({"fs", "img"}, {"inkscape"}),
            "expect": {"status": "ok", "verified": True},
        },
        {
            "id": "gap-recoverable",
            "prior": [],
            "world": lambda: _world({"fs"}, acquirable_schemes={"img"}, acquirable_apps={"inkscape"}),
            "expect": {"status": "ok", "verified": True},
        },
        {
            "id": "gap-unrecoverable-app",
            "prior": [],
            "world": lambda: _world({"fs"}, acquirable_schemes={"img"}, acquirable_apps=set()),
            "expect": {"status": "blocked-need", "verified": False},
        },
        {
            "id": "gap-lying-contract",
            "prior": [],
            "world": lambda: _world(
                {"fs"},
                acquirable_schemes={"img"},
                acquirable_apps={"inkscape"},
                provider=IMG_LYING,
            ),
            "expect": {"status": "blocked-gate", "verified": False},
        },
        {
            "id": "resume-after-fill",
            "prior": ["read_src", "rasterize"],
            "world": lambda: _world({"fs", "img"}, {"inkscape"}, raster=b"PNGDATA"),
            "expect": {"status": "ok", "verified": True},
        },
        {
            "id": "idempotent-rerun",
            "prior": ["read_src", "rasterize", "write_png"],
            "world": lambda: _world(
                {"fs", "img"},
                {"inkscape"},
                raster=b"PNGDATA",
                files={"/tmp/diagram.png": b"PNGDATA"},
            ),
            "expect": {"status": "ok", "verified": True},
        },
    ]


def check(case: dict, result: dict) -> list[str]:
    violations: list[str] = []
    exp = case["expect"]
    if result["status"] != exp["status"]:
        violations.append(f"status: expected {exp['status']} got {result['status']}")
    if result["status"].startswith("blocked") and not (result.get("block") or {}).get("kind"):
        violations.append("blocked without typed need/reason")
    if result["status"] == "ok":
        for acquired in result["acquired"]:
            if not acquired["admitted"] or acquired["violations"]:
                violations.append(
                    f"ungated-acquisition: {acquired['uri']} used despite {acquired['violations']}"
                )
    if result["status"] == "ok" and not result["verified"]:
        violations.append("verify-honesty: status ok but goal is not achieved")
    if result["re_executed"]:
        violations.append(f"restart-instead-of-resume: re-executed {result['re_executed']}")
    return violations


def run_case(case: dict, engine=run_episode) -> dict:
    return engine(GOAL, case["world"](), prior_ledger=case["prior"])


def main() -> int:
    cases = expand()
    passed = 0
    for case in cases:
        result = run_case(case)
        violations = check(case, result)
        passed += not violations
        mark = "ok" if not violations else "fail"
        acquired = "+".join(a["uri"].split("://")[0] for a in result["acquired"]) or "-"
        print(
            f"{mark:4s} {case['id']:22s} status={result['status']:13s} "
            f"verified={str(result['verified']):5s} acquired={acquired}"
        )
        for violation in violations:
            print(f"      - {violation}")
    print(f"\nRESULT: {passed}/{len(cases)} capability-acquisition episodes satisfy all invariants")
    return 0 if passed == len(cases) else 1


if __name__ == "__main__":
    raise SystemExit(main())
