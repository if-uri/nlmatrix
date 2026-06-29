"""Gen 10 — idempotencja powtórzenia.

Obala błędną architekturę: "powtórzenie wykonuje na ślepo ponownie". Wadliwa
architektura na drugie kliknięcie/repeat wykonuje mutację jeszcze raz — dwa
maile zamiast jednego. Honorowy silnik bramkuje komendy kluczem idempotencji:
powtórzenie tej samej operacji jest no-op, query zawsze bezpieczne do powtórki.

Niezmienniki z zębami:
  - liczba mutacji == liczba RÓŻNYCH kluczy idempotencji (powtórka nie dubluje);
  - powtórzenie query → identyczny wynik, zero dodatkowej mutacji.

Uruchom:  python3 gen10_idempotence.py
Testy:    python3 -m pytest test_gen10.py -q

Hak urirun: repeatChatMessage, twin://host/memory/command/remember,
idempotencja tras command.
"""
from __future__ import annotations


def execute(sequence: list[dict]) -> tuple[dict, list[dict]]:
    """Honest: a command carries an idempotency key; a repeat of the same key is a
    no-op. Queries are always safe to repeat."""
    world = {"sent": 0, "queries": 0}
    seen: set[str] = set()
    results: list[dict] = []
    for op in sequence:
        if op["effect"] == "query":
            world["queries"] += 1
            results.append({"value": "LIST", "mutated": False})
            continue
        if op["key"] in seen:
            results.append({"value": "noop", "mutated": False})
            continue
        seen.add(op["key"])
        world["sent"] += 1
        results.append({"value": "sent", "mutated": True})
    return world, results


def buggy_execute(sequence: list[dict]) -> tuple[dict, list[dict]]:
    """The flawed architecture: no idempotency guard — every invocation mutates,
    so a repeat doubles the effect."""
    world = {"sent": 0, "queries": 0}
    results: list[dict] = []
    for op in sequence:
        if op["effect"] == "query":
            world["queries"] += 1
            results.append({"value": "LIST", "mutated": False})
            continue
        world["sent"] += 1
        results.append({"value": "sent", "mutated": True})
    return world, results


# --- ziarno + transformacje --------------------------------------------------
def _send(key):
    return {"id": "send", "effect": "command", "key": key}


def _list():
    return {"id": "list", "effect": "query"}


def expand() -> list[dict]:
    return [
        {"id": "repeat-mutation", "sequence": [_send("mail-7"), _send("mail-7")],
         "expect": {"sent": 1}},
        {"id": "repeat-query", "sequence": [_list(), _list()],
         "expect": {"sent": 0}},
        {"id": "distinct-mutations", "sequence": [_send("mail-7"), _send("mail-8")],
         "expect": {"sent": 2}},
        {"id": "triple-repeat", "sequence": [_send("m"), _send("m"), _send("m")],
         "expect": {"sent": 1}},
    ]


# --- niezmienniki (z zębami) --------------------------------------------------
def check(case: dict, world: dict | tuple[dict, list[dict]], results: list[dict] | None = None) -> list[str]:
    if results is None:
        world, results = world
    v: list[str] = []
    exp = case["expect"]
    if world["sent"] != exp["sent"]:
        v.append(f"sent: expected {exp['sent']} got {world['sent']}")
    # TEETH 1: mutations must equal the number of DISTINCT idempotency keys.
    distinct = {op["key"] for op in case["sequence"] if op["effect"] == "command"}
    if world["sent"] > len(distinct):
        v.append(f"double-mutation: {world['sent']} mutations for {len(distinct)} distinct op(s) "
                 f"— a repeat re-executed blindly")
    # TEETH 2: repeated query must be idempotent (identical result, no mutation).
    qvals = [r["value"] for op, r in zip(case["sequence"], results) if op["effect"] == "query"]
    if len(set(qvals)) > 1:
        v.append("query-not-idempotent: repeated query returned different values")
    return v


def run_case(case: dict, engine=execute):
    return engine(case["sequence"])


def main() -> int:
    cases = expand()
    passed = 0
    for c in cases:
        world, results = run_case(c)
        viol = check(c, world, results)
        ok = not viol
        passed += ok
        print(f"{'✓' if ok else '✗'} {c['id']:20s} sent={world['sent']} queries={world['queries']}")
        for x in viol:
            print(f"      - {x}")
    print(f"\nRESULT: {passed}/{len(cases)} idempotence cases satisfy all invariants")
    return 0 if passed == len(cases) else 1


if __name__ == "__main__":
    raise SystemExit(main())
