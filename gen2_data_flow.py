"""Gen 2 — data-flow między krokami.

Obala błędną architekturę: "kroki są niezależne; referencja do wyniku rozwiązuje
się do wartości domyślnej, gdy źródła brak". Łańcuch `list → capture(monitor_from=…)`
działa dopóki producent zwraca pole — ale wadliwy resolver, gdy źródło jest puste,
**cicho podstawia default** (monitor=0/scope=all) zamiast zablokować. Wtedy zrzut
idzie z całego pulpitu, a `ok:true` kłamie, że "użyto monitora z window-list".

To dokładnie powierzchnia naprawiona w tej sesji (`monitor_from` + sprzeczny
`scope:all`). Niezmienniki z zębami:
  - wartość referowana == wartość producenta;
  - źródło `null`/brak → typed block, NIE cichy default;
  - referencja wymaga `depends_on` i wcześniejszego kroku-producenta.

Uruchom:  python3 gen2_data_flow.py
Testy:    python3 -m pytest test_gen2.py -q

Hak urirun: flow_thin.resolve_step_payload (`<key>_from`), `_dig_path`,
flow_planner._bind_window_monitor_capture, dispatch._flow_scheme_*.
"""
from __future__ import annotations

_MISSING = object()


def _dig(data, dotted: str):
    """Resolve a dotted path; `value` is an optional envelope segment (skip when absent)."""
    cur = data
    for part in dotted.split("."):
        if isinstance(cur, dict):
            if part in cur:
                cur = cur[part]
            elif part == "value":
                continue
            else:
                return _MISSING
        else:
            return _MISSING
    return cur


def _resolve_refs(step: dict, results: dict, *, silent_default):
    """Resolve every ``<key>_from`` in the step payload against prior results.

    Returns (payload, error|None). ``silent_default`` selects the architecture:
    None → honest (missing/null source is an error); a value → flawed (substitute it)."""
    payload = dict(step.get("payload") or {})
    for key in list(payload):
        if not (key.endswith("_from") and isinstance(payload[key], str)):
            continue
        ref = payload[key]
        producer = ref.split(".")[0]
        rest = ref.split(".", 1)[1] if "." in ref else ""
        # honest: a reference must declare its dependency AND the producer must have run
        if silent_default is None:
            if producer not in (step.get("depends_on") or []) or producer not in results:
                return payload, {"reason": "ref-missing-dependency", "ref": ref}
        val = _dig(results.get(producer, {}), rest) if rest else _MISSING
        if val is _MISSING or val is None:
            if silent_default is None:
                return payload, {"reason": "ref-source-null", "ref": ref}
            val = silent_default  # the flawed architecture quietly invents a value
        payload[key[:-len("_from")]] = val
        del payload[key]
    return payload, None


def _run(flow: dict, *, silent_default) -> dict:
    results: dict = {}
    out: list[dict] = []
    for step in flow["steps"]:
        payload, err = _resolve_refs(step, results, silent_default=silent_default)
        if err is not None:
            return {"status": "blocked", "reason": err["reason"], "step": step["id"], "steps": out}
        results[step["id"]] = step.get("produces", {})
        out.append({"id": step["id"], "payload": payload})
    return {"status": "ok", "reason": None, "step": None, "steps": out}


def resolve(flow: dict) -> dict:
    """Honest resolver: a missing/null reference is a typed block, never a default."""
    return _run(flow, silent_default=None)


def buggy_resolve(flow: dict) -> dict:
    """The flawed architecture: a missing/null reference silently resolves to a
    default (monitor=0), and dependency ordering is not enforced."""
    return _run(flow, silent_default=0)


# --- ziarno + transformacje --------------------------------------------------
_LIST = "kvm://host/window/query/list"
_CAP = "kvm://host/screen/query/capture"


def _list_step(produces):
    return {"id": "list", "uri": _LIST, "payload": {"app": "chrome"}, "depends_on": [], "produces": produces}


def _capture_step(depends_on=("list",), ref="list.result.value.selected.monitor"):
    return {"id": "capture", "uri": _CAP, "depends_on": list(depends_on),
            "payload": {"monitor_from": ref}}


def expand() -> list[dict]:
    sel3 = {"result": {"selected": {"monitor": 3}}}
    return [
        {"id": "resolved-ok", "expect": {"status": "ok", "resolved_monitor": 3},
         "flow": {"steps": [_list_step(sel3), _capture_step()]}},
        # source field present but null → must block, not default
        {"id": "source-null", "source_missing": True, "expect": {"status": "blocked", "reason": "ref-source-null"},
         "flow": {"steps": [_list_step({"result": {"selected": {"monitor": None}}}), _capture_step()]}},
        # producer returns no `selected` at all → missing path
        {"id": "source-absent", "source_missing": True, "expect": {"status": "blocked", "reason": "ref-source-null"},
         "flow": {"steps": [_list_step({"result": {}}), _capture_step()]}},
        # consumer before producer (reordered) → dependency not yet satisfied
        {"id": "reordered", "source_missing": True, "expect": {"status": "blocked", "reason": "ref-missing-dependency"},
         "flow": {"steps": [_capture_step(), _list_step(sel3)]}},
        # the reference names a producer that is not present in the flow at all
        {"id": "unknown-producer", "source_missing": True,
         "expect": {"status": "blocked", "reason": "ref-missing-dependency"},
         "flow": {"steps": [_list_step(sel3), _capture_step(depends_on=("missing",),
                                                            ref="missing.result.value.selected.monitor")]}},
        # the producer exists, and is declared, but appears later than the consumer
        {"id": "future-producer", "source_missing": True,
         "expect": {"status": "blocked", "reason": "ref-missing-dependency"},
         "flow": {"steps": [_capture_step(depends_on=("list",)), _list_step(sel3)]}},
        # reference without declaring depends_on → must block (no implicit wiring)
        {"id": "missing-dep", "source_missing": True, "expect": {"status": "blocked", "reason": "ref-missing-dependency"},
         "flow": {"steps": [_list_step(sel3), _capture_step(depends_on=())]}},
        # deep path through the optional `value` envelope segment still resolves
        {"id": "deep-path", "expect": {"status": "ok", "resolved_monitor": 2},
         "flow": {"steps": [_list_step({"result": {"value": {"selected": {"monitor": 2}}}}), _capture_step()]}},
    ]


# --- niezmienniki (z zębami) --------------------------------------------------
def _capture_payload(result: dict):
    for s in result.get("steps", []):
        if s["id"] == "capture":
            return s["payload"]
    return None


def check(case: dict, result: dict) -> list[str]:
    v: list[str] = []
    exp = case["expect"]
    if result["status"] != exp["status"]:
        v.append(f"status: expected {exp['status']} got {result['status']}")
    if exp.get("reason") and result.get("reason") != exp["reason"]:
        v.append(f"reason: expected {exp['reason']} got {result.get('reason')}")
    # value invariant: a resolved reference equals the producer's value
    if exp.get("resolved_monitor") is not None:
        pay = _capture_payload(result) or {}
        if pay.get("monitor") != exp["resolved_monitor"]:
            v.append(f"value: resolved monitor {pay.get('monitor')} != producer {exp['resolved_monitor']}")
    # TEETH: a missing/null source must block — never silently resolve to a default.
    if case.get("source_missing") and result["status"] == "ok":
        pay = _capture_payload(result) or {}
        v.append(f"silent-default: missing source resolved to monitor={pay.get('monitor')} instead of a typed block")
    return v


def run_case(case: dict, engine=resolve) -> dict:
    return engine(case["flow"])


def main() -> int:
    cases = expand()
    passed = 0
    for c in cases:
        res = run_case(c)
        viol = check(c, res)
        ok = not viol
        passed += ok
        print(f"{'✓' if ok else '✗'} {c['id']:16s} status={res['status']:8s} reason={str(res.get('reason')):24s}")
        for x in viol:
            print(f"      - {x}")
    print(f"\nRESULT: {passed}/{len(cases)} data-flow cases satisfy all invariants")
    return 0 if passed == len(cases) else 1


if __name__ == "__main__":
    raise SystemExit(main())
