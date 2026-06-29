#!/usr/bin/env python3
"""Zbiorczy runner drabiny generacji (Gen 2-11).

Egzekwuje META-niezmiennik, na którym stoi cała drabina:

    Generacja jest wartościowa tylko, gdy jej niezmiennik PADA pod konkretną
    błędną architekturą. Więc każda generacja MUSI mieć:
      (1) mutanta w module  — funkcję `buggy_*` / klasę `Buggy*`
          (silnik wcielający błędną architekturę), oraz
      (2) test-mutanta      — test asercjonujący, że ten sam checker, który
          honorowy silnik przechodzi, łapie mutanta.

Brak któregokolwiek = czerwone, niezależnie od tego, czy oracle przechodzi.
Funkcjonalnie: cała drabina test_gen*.py musi być zielona.

Uruchom:  python3 run_ladder.py
"""
from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

# (gen, slug, błędna architektura którą obala)
LADDER = [
    (2, "gen2_data_flow", "referencja → cichy default, gdy brak źródła"),
    (3, "gen3_reversible", "`reversible` to etykieta, nie zdolność"),
    (4, "gen4_state_router", "routing decydowany raz i cache'owany"),
    (5, "gen5_cross_target", "wszystko po cichu spada na host"),
    (6, "gen6_recall_adaptation", "recall odtwarza zapisany flow dosłownie"),
    (7, "gen7_effect_honesty", "niszczycielskość z sentymentu NL (`is_destructive`)"),
    (8, "gen8_verification", "`ok:true` na kroku == zadanie zrobione"),
    (9, "gen9_preference_memory", "preferencja globalna, nie per-fingerprint"),
    (10, "gen10_idempotence", "powtórzenie wykonuje na ślepo ponownie"),
    (11, "gen11_capability_acquisition", "samorozszerzenie omija bramę admisji"),
]


def _module_has_mutant(slug: str) -> bool:
    """The generation's code must contain a flawed-architecture engine."""
    mod = importlib.import_module(slug)
    return any(n.startswith("buggy_") or n.startswith("Buggy") for n in dir(mod))


def _testfile_has_mutant_test(gen: int) -> bool:
    """The generation's tests must assert the mutant is CAUGHT, not just that the
    oracle passes — otherwise the invariant has no teeth."""
    path = HERE / f"test_gen{gen}.py"
    if not path.exists():
        return False
    txt = path.read_text(encoding="utf-8").lower()
    has_mutant_engine = "buggy" in txt           # exercises the flawed engine
    has_catch_assert = (
        "must flag" in txt
        or "checker must" in txt
        or "must be caught" in txt
        or "diverge" in txt
        or "leak" in txt
        or "zlap" in txt
        or "złap" in txt
    )
    return "def test_" in txt and has_mutant_engine and has_catch_assert


def _pytest_green(gen: int) -> tuple[bool, str]:
    path = HERE / f"test_gen{gen}.py"
    if not path.exists():
        return False, "no test file"
    res = subprocess.run([sys.executable, "-m", "pytest", str(path), "-q"],
                         capture_output=True, text=True, cwd=str(HERE))
    last = (res.stdout.strip().splitlines() or ["(no output)"])[-1]
    return res.returncode == 0, last.strip()


def main() -> int:
    rows = []
    all_ok = True
    for gen, slug, bad_arch in LADDER:
        mod_mut = _module_has_mutant(slug)
        test_mut = _testfile_has_mutant_test(gen)
        green, detail = _pytest_green(gen)
        ok = mod_mut and test_mut and green
        all_ok = all_ok and ok
        rows.append((gen, slug, bad_arch, mod_mut, test_mut, green, detail, ok))

    print("Drabina generacji — META-niezmiennik: oracle zielony ∧ mutant w module ∧ test-mutant\n")
    print(f"{'Gen':>3}  {'mutant':6}  {'test':5}  {'green':6}  obala błędną architekturę")
    print("-" * 78)
    for gen, slug, bad_arch, mod_mut, test_mut, green, detail, ok in rows:
        mark = "✓" if ok else "✗"
        print(f"{mark}{gen:>3}  {'✓' if mod_mut else '✗':6}  {'✓' if test_mut else '✗':5}  "
              f"{'✓' if green else '✗':6}  {bad_arch}")
        if not ok:
            print(f"       └─ {detail}")
    done = sum(1 for r in rows if r[-1])
    print(f"\nRESULT: {done}/{len(rows)} generacji spełnia meta-niezmiennik "
          f"(oracle + mutant w kodzie + test-mutant)")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
