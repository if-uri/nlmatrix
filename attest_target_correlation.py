"""Atestacja L11 ↔ L3 — korelacja targetu między warstwami.

Znaleziona w idealnie zielonym śladzie (recall, wszystkie kroki `ok:true`): TA SAMA
operacja ma dwa różne cele w jednej kopercie —
    results[step].target == "host"
    routing.runsOnByStep[step.uri] == "lenovo"
    timeline[step].target == "lenovo"
Wynik kroku mówi „host", routing i timeline mówią „lenovo". W dry-run nikt nie
ucierpiał (`simulated:true`), ale gdyby to był realny capture — na której maszynie
naprawdę zrobiono zrzut? Checklista („czy działa") tego nie złapie: każdy krok ma
`ok:true`. Kłamie dopiero ZGODNOŚĆ między warstwami.

Niezmiennik (z zębami): dla każdego kroku target w `results` MUSI równać się
`runsOn` w routingu i `target` w timeline. To jest L11↔L3 odpowiednik korelacji L2.

Uruchom:  python3 attest_target_correlation.py
Testy:    python3 -m pytest test_attest_target_correlation.py -q
"""
from __future__ import annotations


def attest_target_correlation(trace: dict) -> list[dict]:
    """One entry per step: do results / routing / timeline agree on the target?"""
    results = trace.get("results") or {}
    runs_on = (trace.get("routing") or {}).get("runsOnByStep") or {}
    timeline_target = {t.get("id"): t.get("target") for t in (trace.get("timeline") or []) if isinstance(t, dict)}
    out: list[dict] = []
    for sid, sr in results.items():
        if not isinstance(sr, dict):
            continue
        uri = str(sr.get("invokedUri") or sr.get("uri") or "")
        # Top-level results.target is execution metadata stamped by the flow engine.
        # Nested result.target is connector/domain payload and may be stale or local.
        res_target = sr.get("target")
        if res_target is None and isinstance(sr.get("result"), dict):
            res_target = (sr.get("result") or {}).get("target")
        route_target = runs_on.get(uri)
        tl_target = timeline_target.get(sid)
        seen = {x for x in (res_target, route_target, tl_target) if x is not None}
        ok = len(seen) <= 1
        out.append({"layer": "L11↔L3", "seam": "results↔routing↔timeline", "step": sid, "ok": ok,
                    "detail": f"results={res_target} routing={route_target} timeline={tl_target}"})
    return out


def violations(trace: dict) -> list[dict]:
    return [e for e in attest_target_correlation(trace) if not e["ok"]]


# --- the observed buggy trace (recall, host vs lenovo) + a consistent control ---
BUGGY_TRACE = {
    "routing": {"runsOnByStep": {"kvm://host/screen/query/capture": "lenovo"}},
    "results": {"kvm_host_screen_query_capture": {
        "invokedUri": "kvm://host/screen/query/capture",
        "result": {"target": "host", "kind": "screenshot", "ok": True}}},
    "timeline": [{"id": "kvm_host_screen_query_capture", "target": "lenovo", "ok": True}],
}

FIXED_TRACE = {
    "routing": {"runsOnByStep": {"kvm://host/screen/query/capture": "lenovo"}},
    "results": {"kvm_host_screen_query_capture": {
        "invokedUri": "kvm://host/screen/query/capture",
        "target": "lenovo",
        "result": {"target": "host", "kind": "screenshot", "ok": True}}},
    "timeline": [{"id": "kvm_host_screen_query_capture", "target": "lenovo", "ok": True}],
}

CONSISTENT_TRACE = {
    "routing": {"runsOnByStep": {"kvm://lenovo/screen/query/capture": "lenovo"}},
    "results": {"kvm_host_screen_query_capture": {
        "invokedUri": "kvm://lenovo/screen/query/capture",
        "result": {"target": "lenovo", "kind": "screenshot", "ok": True}}},
    "timeline": [{"id": "kvm_host_screen_query_capture", "target": "lenovo", "ok": True}],
}


def main() -> int:
    bad = violations(BUGGY_TRACE)
    good = violations(CONSISTENT_TRACE)
    for label, viol in (("buggy", bad), ("consistent", good)):
        print(f"{label} trace: {'CORRELATION HOLDS' if not viol else 'MISMATCH'}")
        for e in viol:
            print(f"  ✗ {e['layer']} {e['seam']} [{e['step']}] {e['detail']}")
    # teeth: the attestation MUST flag the buggy trace and pass the consistent one
    ok = bool(bad) and not good
    print(f"\nattestation has teeth: {ok}  (flags buggy={bool(bad)}, passes consistent={not good})")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
