"""Meta-gate for delivered autonomy test generations.

Every generation that claims to validate an architectural invariant must have:

* a deterministic oracle that satisfies its own invariants;
* at least one buggy/mutant engine;
* a checker that catches the mutant on at least one generated case;
* a standalone runner that exits green.

This keeps the test suite focused on "invariants with teeth", not only on
happy-path examples.
"""
from __future__ import annotations

import importlib
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Callable


ROOT = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Generation:
    name: str
    module_name: str
    oracle_name: str
    mutant_name: str
    runner: str

    @property
    def module(self) -> ModuleType:
        return importlib.import_module(self.module_name)

    @property
    def oracle(self) -> Callable:
        return getattr(self.module, self.oracle_name)

    @property
    def mutant(self) -> Callable:
        return getattr(self.module, self.mutant_name)


GENERATIONS = [
    Generation("Gen2", "gen2_data_flow", "resolve", "buggy_resolve", "gen2_data_flow.py"),
    Generation("Gen3", "gen3_reversible", "execute", "buggy_execute", "gen3_reversible.py"),
    Generation("Gen4", "gen4_state_router", "route_and_execute", "buggy_cached_router", "gen4_state_router.py"),
    Generation("Gen5", "gen5_cross_target", "route", "buggy_route", "gen5_cross_target.py"),
    Generation("Gen6", "gen6_recall_adaptation", "adapt_recall", "buggy_literal_recall", "gen6_recall_adaptation.py"),
    Generation("Gen7", "gen7_effect_honesty", "verdict", "buggy_verdict", "gen7_effect_honesty.py"),
    Generation("Gen8", "gen8_verification", "execute", "buggy_execute", "gen8_verification.py"),
    Generation("Gen9", "gen9_preference_memory", "Session", "BuggySession", "gen9_preference_memory.py"),
    Generation("Gen10", "gen10_idempotence", "execute", "buggy_execute", "gen10_idempotence.py"),
    Generation("Gen11", "gen11_capability_acquisition", "run_episode", "buggy_skip_missing",
               "gen11_capability_acquisition.py"),
]


def test_delivered_generations_expose_the_required_surface():
    for gen in GENERATIONS:
        module = gen.module
        for attr in ("expand", "check", "run_case"):
            assert hasattr(module, attr), f"{gen.name} missing {attr}()"
        assert hasattr(module, gen.oracle_name), f"{gen.name} missing oracle {gen.oracle_name}()"
        assert hasattr(module, gen.mutant_name), f"{gen.name} missing mutant {gen.mutant_name}()"
        assert (ROOT / gen.runner).exists(), f"{gen.name} missing runner {gen.runner}"


def test_oracles_satisfy_all_generated_invariants():
    for gen in GENERATIONS:
        module = gen.module
        cases = module.expand()
        assert cases, f"{gen.name} generated no cases"
        for case in cases:
            result = module.run_case(case, engine=gen.oracle)
            violations = module.check(case, result)
            assert violations == [], f"{gen.name} oracle failed {case['id']}: {violations}"


def test_each_generation_catches_its_buggy_architecture():
    for gen in GENERATIONS:
        module = gen.module
        caught: list[tuple[str, list[str]]] = []
        for case in module.expand():
            result = module.run_case(case, engine=gen.mutant)
            violations = module.check(case, result)
            if violations:
                caught.append((case["id"], violations))
        assert caught, f"{gen.name} mutant {gen.mutant_name} was not caught"


def test_standalone_generation_runners_exit_green():
    for gen in GENERATIONS:
        result = subprocess.run(
            [sys.executable, gen.runner],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        assert result.returncode == 0, f"{gen.name} runner failed:\n{result.stdout}"
