"""Dowód: jedna funkcja, każde urządzenie; nowe urządzenie bez kodu; brama trzyma."""
from __future__ import annotations

import importlib

import reuse_via_declarations as r


def _fresh():
    importlib.reload(r)
    return r


def test_one_resolver_handles_every_domain():
    m = _fresh()
    mem = {("audio.default", "env-1"): "usb"}
    assert m.resolve_for("kvm://host/camera/query/snap", {}, m.INVENTORY, mem)["camera"]["via"] == "single"
    assert m.resolve_for("audio://host/sink/command/route", {}, m.INVENTORY, mem)["sink"]["via"] == "remembered"
    assert m.resolve_for("kvm://host/screen/query/capture", {}, m.INVENTORY, mem)["monitor"]["via"] == "ask"


def test_new_device_needs_zero_resolver_code():
    m = _fresh()
    before = m.resolve_slot.__code__.co_code
    m.CONTRACTS["print://host/doc/command/print"] = {"printer": {"domain": "env:printers.id"}}
    m.INVENTORY["env:printers.id"] = [{"value": "hp"}, {"value": "epson"}]
    res = m.resolve_for("print://host/doc/command/print", {}, m.INVENTORY, {})["printer"]
    assert res["via"] == "ask" and res["needs_selection"] == ["hp", "epson"]
    assert m.resolve_slot.__code__.co_code == before


def test_gate_rejects_out_of_domain():
    m = _fresh()
    res = m.resolve_slot("monitor", {"domain": "env:monitors.id"}, {"monitor": 99}, m.INVENTORY, {})
    assert res["blocked"] == "env-domain-invalid" and res["allowed"] == [1, 2, 3]


def test_explicit_in_domain_passes():
    m = _fresh()
    res = m.resolve_slot("monitor", {"domain": "env:monitors.id"}, {"monitor": 2}, m.INVENTORY, {})
    assert res == {"resolved": 2, "via": "explicit"}


def test_dataflow_deferred_to_producer():
    m = _fresh()
    res = m.resolve_slot("monitor", {"domain": "env:monitors.id"},
                         {"monitor_from": "step.result.value"}, m.INVENTORY, {})
    assert res["via"] == "dataflow" and res["deferred"] == "step.result.value"
