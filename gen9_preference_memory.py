"""Gen 9 — selekcja → pamięć → auto-run (per-fingerprint).

Obala błędną architekturę: "preferencja globalna (nie per-fingerprint)". Wadliwa
architektura zapamiętuje wybór bez wiązania go z fingerprintem środowiska, więc
preferencja z układu z dockiem (monitor 3) **przecieka** po odłączeniu docka i
auto-uruchamia się w środowisku, którego nie dotyczy.

Honorowy silnik kluczuje preferencję fingerprintem: auto-run tylko przy zgodnym
fp; inny fp (albo drift) → pyta ponownie. Niezmienniki z zębami:
  - auto-run preferencji **tylko** przy fingerprincie, pod którym zapamiętano;
  - inny fingerprint / drift → ponowne pytanie, nie cichy reuse.

To jest sekwencja interakcji (ambiguous → answer → reuse → inny fp → drift), bo
ta generacja testuje pamięć w czasie, nie pojedynczy strzał.

Uruchom:  python3 gen9_preference_memory.py
Testy:    python3 -m pytest test_gen9.py -q

Hak urirun: remember_preference/recall_preference/_preference_key,
environment_fingerprint, rodzina human-task w dashboard.
"""
from __future__ import annotations


class Session:
    """Honest: preference is keyed by environment fingerprint."""
    def __init__(self):
        self.store: dict[str, int] = {}

    def decide(self, fp: str, options: list[int], answer: int | None = None) -> dict:
        if answer is not None:
            self.store[fp] = answer
            return {"action": "auto-run", "monitor": answer} if answer in options else {"action": "ask"}
        pref = self.store.get(fp)
        if pref is not None and pref in options:
            return {"action": "auto-run", "monitor": pref}
        return {"action": "ask", "monitor": None}


class BuggySession:
    """The flawed architecture: one global preference slot, fingerprint ignored."""
    def __init__(self):
        self.value: int | None = None

    def decide(self, fp: str, options: list[int], answer: int | None = None) -> dict:
        if answer is not None:
            self.value = answer
            return {"action": "auto-run", "monitor": answer}
        if self.value is not None and self.value in options:
            return {"action": "auto-run", "monitor": self.value}  # ignores fp → leaks across environments
        return {"action": "ask", "monitor": None}


# --- ziarno: jedna sekwencja interakcji w czasie ------------------------------
FP_DOCK = "env-dock-3"       # layout z dockiem (3 monitory)
FP_NODOCK = "env-nodock-2"   # dock odłączony (inny fingerprint)


def scenario() -> list[dict]:
    opts3 = [1, 2, 3]
    return [
        {"id": "ambiguous-first", "fp": FP_DOCK, "options": opts3, "answer": None,
         "expect": {"action": "ask"}},
        {"id": "user-answers", "fp": FP_DOCK, "options": opts3, "answer": 3,
         "expect": {"action": "auto-run", "monitor": 3}},
        {"id": "reuse-same-fp", "fp": FP_DOCK, "options": opts3, "answer": None,
         "expect": {"action": "auto-run", "monitor": 3}},
        # different layout, but monitor 3 still EXISTS — a fingerprint-blind store would
        # blindly reuse "3"; the honest store asks because this environment is not the one
        # the preference was remembered under.
        {"id": "different-fp-asks", "fp": FP_NODOCK, "options": opts3, "answer": None,
         "expect": {"action": "ask"}},
        {"id": "back-to-dock-reuse", "fp": FP_DOCK, "options": opts3, "answer": None,
         "expect": {"action": "auto-run", "monitor": 3}},
    ]


def run(session) -> list[dict]:
    return [session.decide(i["fp"], i["options"], i["answer"]) for i in scenario()]


# --- niezmienniki (z zębami) --------------------------------------------------
def check(results: list[dict]) -> list[str]:
    v: list[str] = []
    interactions = scenario()
    remembered: dict[str, int] = {}  # fp -> value remembered so far (replayed)
    for i, (inter, res) in enumerate(zip(interactions, results)):
        exp = inter["expect"]
        if res["action"] != exp["action"]:
            v.append(f"[{inter['id']}] action: expected {exp['action']} got {res['action']}")
        if exp.get("monitor") is not None and res.get("monitor") != exp["monitor"]:
            v.append(f"[{inter['id']}] monitor: expected {exp['monitor']} got {res.get('monitor')}")
        # TEETH: an auto-run with no answer must reuse a preference remembered AT THIS fingerprint.
        if inter["answer"] is None and res["action"] == "auto-run":
            if remembered.get(inter["fp"]) != res.get("monitor"):
                v.append(f"[{inter['id']}] preference-leak: auto-ran monitor={res.get('monitor')} at "
                         f"fingerprint {inter['fp']} with no preference remembered there")
        if inter["answer"] is not None:
            remembered[inter["fp"]] = inter["answer"]
    return v


def main() -> int:
    results = run(Session())
    viol = check(results)
    for inter, res in zip(scenario(), results):
        print(f"  {inter['id']:22s} fp={inter['fp']:14s} -> {res['action']:9s} monitor={res.get('monitor')}")
    for x in viol:
        print(f"  - {x}")
    print(f"\nRESULT: {'PASS' if not viol else 'FAIL'} — {len(scenario())} interactions, "
          f"{len(viol)} invariant violation(s)")
    return 0 if not viol else 1


if __name__ == "__main__":
    raise SystemExit(main())
