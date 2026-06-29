#!/usr/bin/env python3
"""Probe out-of-corpus anchor phrases against the real planner.

The 108-case matrix is a specification of the documented corpus, not a proof over
the open world. This script deliberately uses phrases outside that corpus and
reports whether the planner derives a state-grounded flow, e.g.

    window/query/list -> screen/query/capture(monitor_from=...)

It is a measurement tool, not a default CI gate. Use ``--strict`` when a family
has graduated from "known gap" to required behaviour.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import run as matrix_run  # noqa: E402


CASES = [
    {
        "id": "app-anchor-vscode",
        "prompt": "zrób zrzut monitora, na którym mam VS Code",
        "windows": [{"app": "Visual Studio Code", "title": "main.py - Visual Studio Code", "monitor": 2}],
        "expect": "window-anchor",
    },
    {
        "id": "app-anchor-terminal",
        "prompt": "zrób zrzut ekranu z terminalem",
        "windows": [{"app": "GNOME Terminal", "title": "tom@host:~/github/if-uri", "monitor": 1}],
        "expect": "window-anchor",
    },
    {
        "id": "spatial-near-terminal",
        "prompt": "zrób zrzut ekranu obok terminala",
        "windows": [{"app": "GNOME Terminal", "title": "tom@host:~/github/if-uri", "monitor": 1}],
        "expect": "known-gap:spatial-relation",
    },
    {
        "id": "monitor-descriptor-large",
        "prompt": "zrób zrzut tego dużego monitora",
        "windows": [],
        "expect": "known-gap:monitor-descriptor",
    },
]


def _model_from_env() -> str | None:
    return os.environ.get("URIRUN_LLM_MODEL") or os.environ.get("LLM_MODEL") or None


def _env_for(case: dict) -> list[dict]:
    inventory = {
        "fingerprint": "env-ood-probe",
        "domains": {
            "env:monitors.id": [
                {"value": 1, "label": "HDMI-1", "primary": True},
                {"value": 2, "label": "DP-2"},
                {"value": 3, "label": "DP-1"},
            ],
        },
        "monitors": [
            {"id": 1, "connector": "HDMI-1", "primary": True, "width": 1920, "height": 1080},
            {"id": 2, "connector": "DP-2", "width": 3840, "height": 2160},
            {"id": 3, "connector": "DP-1", "width": 1920, "height": 1080},
        ],
    }
    windows = [dict(w) for w in case.get("windows") or []]
    return [{
        "node": "host",
        "inventory": inventory,
        "domains": inventory["domains"],
        "windows": windows,
        "profile": {
            "platform": "linux-wayland",
            "best": "screen",
            "monitors": inventory["monitors"],
            "windows": windows,
            "cdp": {"reachable": False},
        },
    }]


def _has_window_anchor_flow(flow: dict) -> bool:
    steps = flow.get("steps") or []
    has_window_list = any(str(s.get("uri") or "").endswith("/window/query/list") for s in steps)
    has_monitor_from = any(
        isinstance((s.get("payload") or {}).get("monitor_from"), str)
        for s in steps
        if str(s.get("uri") or "").endswith("/screen/query/capture")
    )
    return has_window_list and has_monitor_from


def _run_case(case: dict, *, use_llm: bool, model: str | None) -> dict:
    matrix_run._ensure_real_paths()
    from urirun_flow.flow_planner import make_flow  # noqa: PLC0415

    mesh = {
        "nodes": [{"name": "host"}],
        "routes": matrix_run._real_routes(),
    }
    try:
        flow, generator = make_flow(
            case["prompt"],
            mesh,
            selected_nodes=["host"],
            use_llm=use_llm,
            environments=_env_for(case),
            llm_model=model,
        )
    except Exception as exc:  # noqa: BLE001
        return {
            "id": case["id"],
            "prompt": case["prompt"],
            "expect": case["expect"],
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
        }
    has_anchor = _has_window_anchor_flow(flow)
    expect = str(case["expect"])
    required = expect == "window-anchor"
    ok = has_anchor if required else True
    return {
        "id": case["id"],
        "prompt": case["prompt"],
        "expect": case["expect"],
        "ok": ok,
        "required": required,
        "hasWindowAnchorFlow": has_anchor,
        "source": (generator or {}).get("provider") or (flow.get("task") or {}).get("source"),
        "generator": generator,
        "steps": [
            {
                "id": s.get("id"),
                "uri": s.get("uri"),
                "payload": s.get("payload") or {},
                "depends_on": s.get("depends_on") or [],
            }
            for s in flow.get("steps") or []
        ],
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--llm", action="store_true")
    ap.add_argument("--model", default=None)
    ap.add_argument("--strict", action="store_true",
                    help="exit non-zero when a required OOD app-anchor fails")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    model = args.model or _model_from_env()
    rows = [_run_case(c, use_llm=args.llm, model=model) for c in CASES]
    required = [r for r in rows if r.get("required")]
    summary = {
        "total": len(rows),
        "required": len(required),
        "requiredPassed": sum(1 for r in required if r.get("ok")),
        "knownGap": sum(1 for r in rows if str(r.get("expect", "")).startswith("known-gap")),
        "llm": bool(args.llm),
        "model": model,
    }
    if args.json:
        print(json.dumps({"summary": summary, "cases": rows}, ensure_ascii=False, indent=2))
    else:
        for row in rows:
            mark = "✓" if row.get("ok") else "✗"
            req = "required" if row.get("required") else "probe"
            print(f"{mark} {row['id']:26s} {req:8s} anchor={row.get('hasWindowAnchorFlow')} "
                  f"source={row.get('source')} :: {row['prompt']}")
            if row.get("error"):
                print(f"      - {row['error']}")
        print(f"\nRESULT: {summary['requiredPassed']}/{summary['required']} required OOD anchors passed; "
              f"{summary['knownGap']} known-gap probe(s)")
    return 1 if args.strict and summary["requiredPassed"] != summary["required"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
