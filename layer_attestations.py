"""Atestacje warstwowe — jak przypisać anomalię do właściwej warstwy.

Zasada: anomalię lokalizuje PIERWSZA atestacja szwu, która pada. Pytanie "przed"
(precondycja) łapie błędy rozumowania; pytanie "po" (postcondycja) łapie błędy
danych. Bug DP-2/DP-1 był błędem danych w warstwie 8 (window/query/list →
inventory): okno Chrome przypisane do DP-1, choć jest na DP-2.

Kluczowy punkt: błędu danych NIE złapie sprawdzenie czytające tylko podejrzaną
wartość, ani samospójność w dół (zła wartość propaguje: capture weźmie ten sam
zły monitor, więc captured==selected przejdzie). Łapie go REDUNDANCJA — ten sam
fakt wyprowadzony dwiema niezależnymi drogami: geometria (inventory) i nazwa
konektora (AT-SPI). Jeśli się nie zgadzają, warstwa kłamie.

Uruchom:  python3 layer_attestations.py
Testy:    python3 -m pytest test_attestations.py -q
"""
from __future__ import annotations

from typing import Any

# --- inventory z Twojego śladu (3 monitory, geometria logiczna) ---------------
INVENTORY = {
    "fingerprint": "env-4114674116",
    "monitors": [
        {"value": 1, "connector": "HDMI-1", "geometry": {"x": 0, "y": 1609, "width": 2048, "height": 1280}, "primary": True},
        {"value": 2, "connector": "DP-2", "geometry": {"x": 2048, "y": 0, "width": 3840, "height": 2160}, "primary": False},
        {"value": 3, "connector": "DP-1", "geometry": {"x": 0, "y": 329, "width": 2048, "height": 1280}, "primary": False},
    ],
}


def _by_id(inv: dict) -> dict:
    return {m["value"]: m for m in inv["monitors"]}


def _by_connector(inv: dict) -> dict:
    return {m["connector"]: m for m in inv["monitors"]}


def _contains(geom: dict, x: float, y: float) -> bool:
    return geom["x"] <= x < geom["x"] + geom["width"] and geom["y"] <= y < geom["y"] + geom["height"]


def _monitor_by_geometry(inv: dict, bbox_global: list[int]) -> int | None:
    """Niezależna droga #1: który monitor zawiera środek okna (z geometrii inventory)."""
    cx = bbox_global[0] + bbox_global[2] / 2
    cy = bbox_global[1] + bbox_global[3] / 2
    for m in inv["monitors"]:
        if _contains(m["geometry"], cx, cy):
            return m["value"]
    return None


# =============================================================================
# L8 — inventory: postcondycja z REDUNDANCJĄ (to łapie DP-2)
# =============================================================================
def attest_inventory_window(window: dict, inv: dict) -> list[dict]:
    """Monitor okna musi się zgadzać wyprowadzony NIEZALEŻNIE: z geometrii ORAZ
    z nazwy konektora. Reported id musi równać się obu."""
    out: list[dict] = []
    reported = window.get("monitor")

    # droga #2: nazwa konektora (z innego pola AT-SPI niż mapowanie geometrii)
    conn = window.get("monitorConnector")
    by_conn = _by_connector(inv).get(conn)
    if by_conn is not None and by_conn["value"] != reported:
        out.append({"layer": "L8-inventory", "seam": "window→monitor",
                    "ok": False, "detail":
                    f"window.monitor={reported} przeczy monitorConnector={conn} "
                    f"(w inventory to id {by_conn['value']})"})

    # droga #1: geometria (gdy znamy globalny bbox — najsilniejsza, w pełni niezależna)
    bbox = window.get("bbox_global")
    if bbox:
        geo_id = _monitor_by_geometry(inv, bbox)
        if geo_id is not None and geo_id != reported:
            cx = bbox[0] + bbox[2] / 2
            cy = bbox[1] + bbox[3] / 2
            out.append({"layer": "L8-inventory", "seam": "window→monitor",
                        "ok": False, "detail":
                        f"window.monitor={reported}, ale środek okna ({cx:.0f},{cy:.0f}) "
                        f"leży na monitorze {geo_id} ({_by_id(inv)[geo_id]['connector']})"})

    if not out:
        out.append({"layer": "L8-inventory", "seam": "window→monitor", "ok": True,
                    "detail": f"monitor={reported} potwierdzony geometrią i konektorem"})
    return out


# =============================================================================
# L11 — executor: samospójność w DÓŁ (pokazujemy, że SAMA nie wystarcza)
# =============================================================================
def attest_capture_consistency(captured_monitor: int, selected_monitor: int) -> list[dict]:
    """captured == selected. UWAGA: to przechodzi nawet przy błędzie danych z L8,
    bo zła wartość propaguje — dlatego potrzebna jest redundancja w L8, nie tylko
    spójność tutaj."""
    ok = captured_monitor == selected_monitor
    return [{"layer": "L11-executor", "seam": "selected→captured", "ok": ok,
             "detail": f"captured={captured_monitor} {'==' if ok else '!='} selected={selected_monitor}"}]


def run_attestations(trace: dict) -> list[dict]:
    """Złóż log atestacji ze wszystkich szwów. Pierwsza ok:False = atrybucja."""
    inv = trace["inventory"]
    log: list[dict] = []
    log += attest_inventory_window(trace["selected_window"], inv)
    log += attest_capture_consistency(trace["captured_monitor"],
                                      trace["selected_window"]["monitor"])
    return log


def attribution(log: list[dict]) -> dict | None:
    """Pierwsza czerwona atestacja — to ona wskazuje winną warstwę."""
    for entry in log:
        if not entry["ok"]:
            return entry
    return None


# --- demonstracja na danych ze śladu -----------------------------------------
CORRECT = {
    "inventory": INVENTORY,
    "selected_window": {"app": "Google Chrome", "monitor": 2, "monitorConnector": "DP-2",
                        "bbox_global": [2048, 0, 2113, 1592]},
    "captured_monitor": 2,
}
# bug: AT-SPI źle zmapował okno na DP-1 (id 3), choć jest na DP-2
BUG = {
    "inventory": INVENTORY,
    "selected_window": {"app": "Google Chrome", "monitor": 3, "monitorConnector": "DP-2",
                        "bbox_global": [2048, 0, 2113, 1592]},
    "captured_monitor": 3,  # capture wzięło zły monitor (propagacja)
}


def _show(name: str, trace: dict) -> None:
    log = run_attestations(trace)
    print(f"\n=== {name} ===")
    for e in log:
        print(f"  {'✓' if e['ok'] else '✗'} {e['layer']:14s} {e['seam']:18s} {e['detail']}")
    fault = attribution(log)
    if fault:
        print(f"  → ATRYBUCJA: {fault['layer']} — {fault['detail']}")
    else:
        print("  → brak anomalii")


def main() -> int:
    _show("ślad poprawny (DP-2)", CORRECT)
    _show("ślad z bugiem (DP-1 mislabel)", BUG)
    print("\nUwaga: w buggym śladzie L11 (captured==selected) jest ZIELONE — "
          "samospójność w dół nie łapie błędu danych. Łapie go dopiero "
          "redundancja w L8 (geometria vs konektor).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
