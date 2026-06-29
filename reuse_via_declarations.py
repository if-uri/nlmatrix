"""Mniej kodu, więcej interop — dowód wykonalności.

Teza: orchestracja jako dane, nie kod. Jeden uniwersalny resolver slotów obsługuje
każdy parametr env-enum (monitor, kamera, sink audio, drukarka, ...) czytając z
kontraktu pole ``domain``. Dodanie urządzenia = dopisanie deklaracji, zero nowego
kodu. Brama dalej trzyma: wartość spoza domeny daje typed block.
"""
from __future__ import annotations


def resolve_slot(param: str, decl: dict, intent: dict, inventory: dict, memory: dict) -> dict:
    """Resolve one contract-declared env-enum slot.

    Order: explicit -> dataflow -> single -> remembered -> needs-selection.
    The resolver does not know whether the slot is a monitor, camera, printer, or audio sink.
    """
    options = inventory.get(decl["domain"], [])
    values = [opt["value"] for opt in options]

    if (chosen := intent.get(param)) is not None:
        if chosen in values:
            return {"resolved": chosen, "via": "explicit"}
        return {"blocked": "env-domain-invalid", "allowed": values}

    if intent.get(f"{param}_from"):
        return {"deferred": intent[f"{param}_from"], "via": "dataflow"}

    if len(values) == 1:
        return {"resolved": values[0], "via": "single"}

    pref = memory.get((decl.get("preference"), inventory.get("fingerprint")))
    if pref is not None and pref in values:
        return {"resolved": pref, "via": "remembered"}

    if not values:
        return {"blocked": "no-options"}
    return {"needs_selection": values, "via": "ask"}


CONTRACTS: dict[str, dict] = {
    "kvm://host/screen/query/capture": {
        "monitor": {"domain": "env:monitors.id", "preference": "screen.capture.default"},
    },
    "kvm://host/camera/query/snap": {
        "camera": {"domain": "env:cameras.id", "preference": "camera.default"},
    },
    "audio://host/sink/command/route": {
        "sink": {"domain": "env:audio_sinks.id", "preference": "audio.default"},
    },
}

INVENTORY = {
    "fingerprint": "env-1",
    "env:monitors.id": [{"value": 1}, {"value": 2}, {"value": 3}],
    "env:cameras.id": [{"value": 0}],
    "env:audio_sinks.id": [{"value": "hdmi"}, {"value": "usb"}],
}


def resolve_for(uri: str, intent: dict, inventory: dict, memory: dict) -> dict:
    """Resolve every slot declared by a URI contract using the same resolver."""
    return {
        param: resolve_slot(param, decl, intent, inventory, memory)
        for param, decl in CONTRACTS[uri].items()
    }


def main() -> int:
    mem = {("audio.default", "env-1"): "usb"}

    print("=== one resolver, three devices ===")
    print("monitor:", resolve_for("kvm://host/screen/query/capture", {}, INVENTORY, mem)["monitor"])
    print("camera :", resolve_for("kvm://host/camera/query/snap", {}, INVENTORY, mem)["camera"])
    print("audio  :", resolve_for("audio://host/sink/command/route", {}, INVENTORY, mem)["sink"])

    print("\n=== new device = data only ===")
    CONTRACTS["print://host/doc/command/print"] = {
        "printer": {"domain": "env:printers.id", "preference": "printer.default"},
    }
    INVENTORY["env:printers.id"] = [{"value": "hp"}, {"value": "epson"}]
    print("printer:", resolve_for("print://host/doc/command/print", {}, INVENTORY, mem)["printer"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
