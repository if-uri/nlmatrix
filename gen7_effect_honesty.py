"""Gen 7 — uczciwość efektu.

Obala błędną architekturę: "niszczycielskość wnioskowana z sentymentu NL"
(`task_planner.is_destructive`). Wadliwa architektura zgaduje efekt ze słów
promptu: operacja destrukcyjna sformułowana łagodnie ("posprzątaj") przechodzi,
a benigna brzmiąca groźnie ("zniszcz ten bałagan i pokaż") jest blokowana.

Honorowy silnik czyta `contract.effect`/`reversible` z deklaracji trasy — werdykt
jest **funkcją operacji, nie słów**. Niezmiennik metamorficzny z zębami: ten sam
URI daje **identyczny** werdykt destrukcyjności przy każdym sformułowaniu.

Uruchom:  python3 gen7_effect_honesty.py
Testy:    python3 -m pytest test_gen7.py -q

Hak urirun: task_planner.is_destructive (zapach do obalenia), contract.effect,
router route_is_safe/effect_of, gate checkEffect.
"""
from __future__ import annotations

# Declared route contracts — the single source of truth for effect/reversibility.
REGISTRY = {
    "fs://host/file/command/delete": {"effect": "command", "reversible": False},   # destructive
    "mail://host/msg/command/send": {"effect": "command", "reversible": False},    # destructive (leaves system)
    "win://host/window/command/close": {"effect": "command", "reversible": True},  # mutating but reversible
    "fs://host/dir/query/list": {"effect": "query", "reversible": True},           # benign read
    "kvm://host/screen/query/capture": {"effect": "query", "reversible": True},    # benign read
}

# The flawed architecture's lexicon (the is_destructive smell).
_DESTRUCTIVE_WORDS = {"usun", "usuń", "skasuj", "zniszcz", "wyczysc", "wyczyść",
                      "delete", "remove", "destroy", "wipe", "kasuj"}


def _strip(s: str) -> str:
    return s.lower()


def verdict(uri: str, prompt: str) -> dict:
    """Honest: destructiveness is read from the contract, not the prompt. A command
    that cannot be reversed needs confirmation; queries and reversible commands do not."""
    reg = REGISTRY.get(uri, {"effect": "command", "reversible": False})
    destructive = reg["effect"] == "command" and not reg["reversible"]
    return {"uri": uri, "effect": reg["effect"], "destructive": destructive,
            "gate": "block-needs-confirm" if destructive else "allow", "source": "contract"}


def buggy_verdict(uri: str, prompt: str) -> dict:
    """The flawed architecture: infer destructiveness from NL sentiment. A gentle
    euphemism over a real delete passes; a scary word over a read is blocked."""
    words = set(_strip(prompt).split())
    destructive = bool(words & _DESTRUCTIVE_WORDS)
    return {"uri": uri, "effect": "?", "destructive": destructive,
            "gate": "block-needs-confirm" if destructive else "allow", "source": "nl-sentiment"}


# --- ziarno + transformacje (to samo URI, różne sformułowania) ----------------
def expand() -> list[dict]:
    DEL = "fs://host/file/command/delete"
    LIST = "fs://host/dir/query/list"
    CLOSE = "win://host/window/command/close"
    rows = [
        # a real destructive op, phrased from blunt to euphemistic — all destructive
        (DEL, "usuń stare pliki", True),
        (DEL, "posprzątaj w katalogu pobrane", True),
        (DEL, "ogarnij ten bałagan na dysku", True),
        (DEL, "zrób trochę miejsca, jest pełno", True),
        # a benign read, phrased from plain to alarming — never destructive
        (LIST, "pokaż pliki w katalogu", False),
        (LIST, "zniszcz cały ten bałagan i pokaż co zostało", False),
        (LIST, "skasuj wątpliwości i wylistuj zawartość", False),
        # a reversible mutation — gated as reversible, not as destructive
        (CLOSE, "zamknij okno chrome", False),
        (CLOSE, "usuń to okno z ekranu", False),
    ]
    return [{"id": f"{uri.split('://')[1].split('/')[-1]}-{i}", "uri": uri, "prompt": prompt,
             "expect": {"destructive": dest}} for i, (uri, prompt, dest) in enumerate(rows)]


# --- niezmienniki (z zębami) --------------------------------------------------
def check(case: dict, result: dict) -> list[str]:
    v: list[str] = []
    exp = case["expect"]
    if result["destructive"] != exp["destructive"]:
        if exp["destructive"]:
            v.append(f"effect-from-sentiment: destructive op '{case['uri']}' allowed because NL "
                     f"sounded gentle ({case['prompt']!r})")
        else:
            v.append(f"effect-from-sentiment: benign op '{case['uri']}' blocked because NL "
                     f"sounded scary ({case['prompt']!r})")
    return v


def metamorphic_invariance(engine) -> list[str]:
    """Same URI must yield the same destructive verdict across all phrasings."""
    by_uri: dict[str, set] = {}
    for c in expand():
        by_uri.setdefault(c["uri"], set()).add(engine(c["uri"], c["prompt"])["destructive"])
    return [f"verdict varies by phrasing for {uri}: {sorted(vals)}"
            for uri, vals in by_uri.items() if len(vals) > 1]


def run_case(case: dict, engine=verdict) -> dict:
    return engine(case["uri"], case["prompt"])


def main() -> int:
    cases = expand()
    passed = 0
    for c in cases:
        res = run_case(c)
        viol = check(c, res)
        ok = not viol
        passed += ok
        print(f"{'✓' if ok else '✗'} {c['id']:12s} destructive={str(res['destructive']):5s} :: {c['prompt']}")
        for x in viol:
            print(f"      - {x}")
    drift = metamorphic_invariance(verdict)
    print(f"\nmetamorphic invariance (honest): {'OK' if not drift else drift}")
    print(f"RESULT: {passed}/{len(cases)} effect-honesty cases satisfy all invariants")
    return 0 if passed == len(cases) and not drift else 1


if __name__ == "__main__":
    raise SystemExit(main())
