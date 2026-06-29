"""Atestacja musi mieć zęby i lokalizować właściwą warstwę. Te testy dowodzą:
  1. poprawny ślad → zero anomalii,
  2. bug DP-2 → atrybucja do L8 (inventory), nie do plannera/routera,
  3. redundancja jest KONIECZNA: samospójność w dół (L11) przepuszcza ten bug.
"""
import layer_attestations as la


def test_correct_trace_has_no_anomaly():
    log = la.run_attestations(la.CORRECT)
    assert all(e["ok"] for e in log)
    assert la.attribution(log) is None


def test_bug_is_attributed_to_inventory_layer():
    log = la.run_attestations(la.BUG)
    fault = la.attribution(log)
    assert fault is not None
    assert fault["layer"] == "L8-inventory", \
        "błąd danych musi być przypisany do warstwy 8, nie do plannera/routera"


def test_geometry_and_connector_both_fire_on_bug():
    failures = [e for e in la.attest_inventory_window(la.BUG["selected_window"], la.INVENTORY)
                if not e["ok"]]
    details = " ".join(e["detail"] for e in failures)
    assert "monitorConnector" in details   # droga przez nazwę konektora
    assert "leży na monitorze 2" in details  # droga przez geometrię


def test_downstream_self_consistency_MISSES_the_data_bug():
    # to jest sedno: captured==selected przechodzi, bo zła wartość propaguje.
    log = la.attest_capture_consistency(la.BUG["captured_monitor"],
                                        la.BUG["selected_window"]["monitor"])
    assert all(e["ok"] for e in log), \
        "samospójność w dół NIE łapie błędu danych — dlatego potrzebna redundancja w L8"


def test_independent_geometry_catches_even_if_connector_shares_the_fault():
    # gdyby obie pochodziły z tego samego zepsutego pola, cross-field by nie złapał;
    # geometria jest w pełni niezależna od AT-SPI i łapie i tak.
    window = {"monitor": 3, "monitorConnector": "DP-1",  # konektor też zły (wspólne źródło)
              "bbox_global": [2048, 0, 2113, 1592]}       # ale okno jest fizycznie na DP-2
    failures = [e for e in la.attest_inventory_window(window, la.INVENTORY) if not e["ok"]]
    assert any("leży na monitorze 2" in e["detail"] for e in failures), \
        "geometryczna korroboracja musi złapać bug nawet gdy nazwa konektora dzieli usterkę"
