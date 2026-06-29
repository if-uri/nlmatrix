"""Gen 6 - recall adaptation.

Obala bledna architekture: "recall odtwarza zapisany flow doslownie". Taki
system bierze znany epizod z pamieci i wykonuje jego payloady literalnie:
monitor=3, endpoint=cdp-9222, scope=all, itp. Dziala tylko dopoki srodowisko
jest identyczne. Po drifcie monitora albo zmianie fingerprintu robi zla rzecz
albo obchodzi brame env-enum.

Poprawna architektura traktuje recall jako PROPOZYCJE:
  - ten sam fingerprint + wartosci nadal w domenie -> reuse ok;
  - inny fingerprint -> re-resolve wartosci srodowiskowe;
  - result-ref (`monitor_from`) jest preferowany, bo rozstrzyga sie w chwili
    wykonania z aktualnego window/query/list;
  - stale concrete env value poza domena -> typed block/replan, nie replay;
  - preferencja zapamietana pod innym fingerprintem nie przecieka.

Uruchom:  python3 gen6_recall_adaptation.py
Testy:    python3 -m pytest test_gen6.py -q

Hak urirun: TwinMemory.recall_flow_by_intent/recall_episode,
experience_retrieval, environment_fingerprint, env_selection.recall_env_enum_replan_required,
resolve_env_enums.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Env:
    fingerprint: str
    monitors: tuple[int, ...]
    chrome_on_monitor: int | None = None


@dataclass(frozen=True)
class Episode:
    fingerprint: str
    flow: dict
    intent: dict
    preference: int | None = None


def _capture_step(flow: dict) -> dict | None:
    for step in flow.get("steps") or []:
        if str(step.get("uri") or "").endswith("/screen/query/capture"):
            return step
    return None


def _has_window_ref(flow: dict) -> bool:
    cap = _capture_step(flow)
    payload = (cap or {}).get("payload") or {}
    return isinstance(payload.get("monitor_from"), str)


def _flow_with_monitor(monitor: int) -> dict:
    return {
        "steps": [
            {"id": "capture", "uri": "kvm://host/screen/query/capture",
             "payload": {"monitor": monitor}, "depends_on": []}
        ]
    }


def _flow_with_chrome_ref() -> dict:
    return {
        "steps": [
            {"id": "list_chrome_windows", "uri": "kvm://host/window/query/list",
             "payload": {"app": "chrome"}, "depends_on": []},
            {"id": "capture_chrome_monitor", "uri": "kvm://host/screen/query/capture",
             "payload": {"monitor_from": "list_chrome_windows.result.value.selected.monitor"},
             "depends_on": ["list_chrome_windows"]},
        ]
    }


def _resolve_monitor_from_flow(flow: dict, env: Env) -> int | None:
    cap = _capture_step(flow)
    if not cap:
        return None
    payload = cap.get("payload") or {}
    if payload.get("monitor_from"):
        return env.chrome_on_monitor
    if "monitor" in payload:
        try:
            return int(payload["monitor"])
        except Exception:
            return None
    return None


def _block(reason: str, episode: Episode, env: Env, flow: dict | None = None) -> dict:
    return {
        "status": "blocked",
        "reason": reason,
        "episodeFp": episode.fingerprint,
        "envFp": env.fingerprint,
        "flow": flow or episode.flow,
        "monitor": None,
    }


def adapt_recall(episode: Episode, env: Env) -> dict:
    """Honest recall: proposal -> current-env admission -> executable plan."""
    proposed = deepcopy(episode.flow)
    cap = _capture_step(proposed)
    payload = (cap or {}).get("payload") or {}

    if _has_window_ref(proposed):
        monitor = _resolve_monitor_from_flow(proposed, env)
        if monitor is None:
            return _block("anchor-window-not-found", episode, env, proposed)
        if monitor not in env.monitors:
            return _block("anchor-monitor-invalid", episode, env, proposed)
        return {
            "status": "ok", "reason": "result-ref", "source": "recall-adapted",
            "episodeFp": episode.fingerprint, "envFp": env.fingerprint,
            "flow": proposed, "monitor": monitor,
        }

    # Same environment, still valid concrete env value: literal reuse is acceptable.
    if episode.fingerprint == env.fingerprint and "monitor" in payload:
        monitor = _resolve_monitor_from_flow(proposed, env)
        if monitor in env.monitors:
            return {
                "status": "ok", "reason": "same-fingerprint-reuse", "source": "recall",
                "episodeFp": episode.fingerprint, "envFp": env.fingerprint,
                "flow": proposed, "monitor": monitor,
            }

    # Different environment: concrete env values from recall are evidence, not authority.
    if (episode.intent or {}).get("anchor") == "chrome":
        if env.chrome_on_monitor is None:
            return _block("anchor-window-not-found", episode, env, proposed)
        if env.chrome_on_monitor not in env.monitors:
            return _block("anchor-monitor-invalid", episode, env, proposed)
        flow = _flow_with_chrome_ref()
        return {
            "status": "ok", "reason": "re-resolved-from-anchor", "source": "recall-adapted",
            "episodeFp": episode.fingerprint, "envFp": env.fingerprint,
            "flow": flow, "monitor": env.chrome_on_monitor,
        }

    if episode.preference is not None and episode.fingerprint == env.fingerprint:
        if episode.preference in env.monitors:
            flow = _flow_with_monitor(episode.preference)
            return {
                "status": "ok", "reason": "same-fingerprint-preference", "source": "preference",
                "episodeFp": episode.fingerprint, "envFp": env.fingerprint,
                "flow": flow, "monitor": episode.preference,
            }

    return _block("replan-required", episode, env, proposed)


def buggy_literal_recall(episode: Episode, env: Env) -> dict:
    """Flawed architecture: execute the recalled flow exactly as stored."""
    flow = deepcopy(episode.flow)
    monitor = _resolve_monitor_from_flow(flow, env)
    return {
        "status": "ok",
        "reason": "literal-replay",
        "source": "recall",
        "episodeFp": episode.fingerprint,
        "envFp": env.fingerprint,
        "flow": flow,
        "monitor": monitor,
    }


def expand() -> list[dict]:
    return [
        {
            "id": "same-fingerprint-valid",
            "episode": Episode("fp-A", _flow_with_monitor(3), {"anchor": None}),
            "env": Env("fp-A", (1, 2, 3), chrome_on_monitor=3),
            "expect": {"status": "ok", "reason": "same-fingerprint-reuse", "monitor": 3},
        },
        {
            "id": "drifted-fingerprint-reanchor",
            "episode": Episode("fp-A", _flow_with_monitor(3), {"anchor": "chrome"}),
            "env": Env("fp-B", (1, 2), chrome_on_monitor=2),
            "expect": {"status": "ok", "reason": "re-resolved-from-anchor", "monitor": 2,
                       "requiresResultRef": True},
        },
        {
            "id": "same-fingerprint-but-monitor-gone",
            "episode": Episode("fp-A", _flow_with_monitor(3), {"anchor": None}),
            "env": Env("fp-A", (1, 2), chrome_on_monitor=2),
            "expect": {"status": "blocked", "reason": "replan-required", "monitor": None},
        },
        {
            "id": "result-ref-survives-drift",
            "episode": Episode("fp-A", _flow_with_chrome_ref(), {"anchor": "chrome"}),
            "env": Env("fp-B", (1, 2), chrome_on_monitor=2),
            "expect": {"status": "ok", "reason": "result-ref", "monitor": 2,
                       "requiresResultRef": True},
        },
        {
            "id": "anchor-window-closed",
            "episode": Episode("fp-A", _flow_with_monitor(3), {"anchor": "chrome"}),
            "env": Env("fp-B", (1, 2), chrome_on_monitor=None),
            "expect": {"status": "blocked", "reason": "anchor-window-not-found", "monitor": None},
        },
        {
            "id": "old-preference-does-not-leak",
            "episode": Episode("fp-A", _flow_with_monitor(3), {"anchor": None}, preference=3),
            "env": Env("fp-B", (1, 2), chrome_on_monitor=2),
            "expect": {"status": "blocked", "reason": "replan-required", "monitor": None},
        },
        {
            "id": "same-fingerprint-preference-ok",
            "episode": Episode("fp-A", {"steps": []}, {"anchor": None}, preference=2),
            "env": Env("fp-A", (1, 2), chrome_on_monitor=1),
            "expect": {"status": "ok", "reason": "same-fingerprint-preference", "monitor": 2},
        },
    ]


def check(case: dict, result: dict) -> list[str]:
    v: list[str] = []
    exp = case["expect"]
    env = case["env"]
    if result.get("status") != exp.get("status"):
        v.append(f"status: expected {exp.get('status')} got {result.get('status')}")
    if result.get("reason") != exp.get("reason"):
        v.append(f"reason: expected {exp.get('reason')} got {result.get('reason')}")
    if result.get("monitor") != exp.get("monitor"):
        v.append(f"monitor: expected {exp.get('monitor')} got {result.get('monitor')}")

    monitor = result.get("monitor")
    if result.get("status") == "ok" and monitor not in env.monitors:
        v.append(f"stale-env-value: monitor {monitor} not in current inventory {list(env.monitors)}")

    if result.get("episodeFp") != result.get("envFp"):
        cap = _capture_step(result.get("flow") or {})
        payload = (cap or {}).get("payload") or {}
        if "monitor" in payload and result.get("status") == "ok":
            v.append("literal-recall-across-fingerprint: concrete env value reused after drift")
        pref = case["episode"].preference
        if pref is not None and result.get("monitor") == pref and result.get("status") == "ok":
            v.append("preference-fingerprint-leak: old preference reused under new fingerprint")

    if exp.get("requiresResultRef") and not _has_window_ref(result.get("flow") or {}):
        v.append("missing-current-state-reference: adapted recall should use monitor_from")
    return v


def run_case(case: dict, engine=adapt_recall) -> dict:
    return engine(case["episode"], case["env"])


def main() -> int:
    cases = expand()
    passed = 0
    for c in cases:
        res = run_case(c)
        viol = check(c, res)
        ok = not viol
        passed += ok
        mark = "✓" if ok else "✗"
        print(f"{mark} {c['id']:32s} status={res['status']:8s} "
              f"reason={res['reason']:28s} monitor={res.get('monitor')}")
        for x in viol:
            print(f"      - {x}")
    print(f"\nRESULT: {passed}/{len(cases)} recall-adaptation cases satisfy all invariants")
    return 0 if passed == len(cases) else 1


if __name__ == "__main__":
    raise SystemExit(main())
