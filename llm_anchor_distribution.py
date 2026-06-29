#!/usr/bin/env python3
"""Measure the live LLM anchor path as a distribution, not a single anecdote.

The script sends anchor prompts to the chat API with no_llm=false and records:
accepted plans, planner errors, live invariant violations and latency percentiles.
By default it reads the model from URIRUN_LLM_MODEL, then LLM_MODEL, then the
dashboard's non-secret /api/chat/config, so the tested request is explicit when
the process or server advertises a model.

Examples:
  python3 llm_anchor_distribution.py --runs 3 --limit 3
  python3 llm_anchor_distribution.py --model openrouter/google/gemini-3.5-flash
  python3 llm_anchor_distribution.py --json
"""
from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.request

import live_adapt
import live_properties as lp
import live_run


def _percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    idx = int(round((len(ordered) - 1) * pct))
    return ordered[max(0, min(idx, len(ordered) - 1))]


def _model_from_env() -> str | None:
    return os.environ.get("URIRUN_LLM_MODEL") or os.environ.get("LLM_MODEL") or None


def _model_from_server_config(base: str, timeout: float) -> str | None:
    try:
        with urllib.request.urlopen(base.rstrip("/") + "/api/chat/config", timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError):
        return None
    model = str(payload.get("model") or "").strip()
    return model or None


def _generator_source(envelope: dict) -> str | None:
    gen = envelope.get("generator")
    if isinstance(gen, dict):
        for key in ("source", "provider", "planner", "intent"):
            if gen.get(key):
                return str(gen[key])
    if envelope.get("source"):
        return str(envelope["source"])
    return None


def _generator_reason(envelope: dict) -> str | None:
    gen = envelope.get("generator")
    if isinstance(gen, dict) and gen.get("reason"):
        return str(gen["reason"])[:200]
    return None


def _flow_has_window_anchor(adapted: dict) -> bool:
    steps = (adapted.get("flow", {}) or {}).get("steps", []) or []
    has_window_list = any(str(s.get("uri") or "").endswith("/window/query/list") for s in steps)
    has_monitor_from = any(
        isinstance((s.get("payload") or {}).get("monitor_from"), str)
        for s in steps
    )
    return has_window_list and has_monitor_from


def run_once(*, url: str, prompt_meta: dict, targets: list[str], discovery: str,
             execute: int, model: str | None, timeout: float) -> dict:
    body = live_run.build_body(
        prompt_meta["intent"],
        targets,
        execute,
        discovery,
        no_llm=False,
        model=model,
    )
    started = time.monotonic()
    try:
        envelope = live_run.post_json(url, body, timeout)
        elapsed = time.monotonic() - started
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError) as exc:
        return {
            "intent": prompt_meta["intent"],
            "ok": False,
            "elapsed": time.monotonic() - started,
            "error": str(exc),
            "model": body.get("model"),
        }

    adapted = live_adapt.adapt(envelope)
    if lp.kind(adapted) == "planner-error":
        return {
            "intent": prompt_meta["intent"],
            "kind": "planner-error",
            "ok": None,
            "elapsed": elapsed,
            "model": body.get("model"),
            "source": _generator_source(envelope),
            "generatorReason": _generator_reason(envelope),
            "error_message": adapted.get("error_message"),
        }

    violations = (
        lp.check_invariants(adapted)
        + lp.check_self_consistency(adapted)
        + lp.expected_from_prompt(prompt_meta, adapted)
        + lp.check_correlation(prompt_meta, adapted, request_no_llm=False)
        + lp.check_needs_selection_autonomy(prompt_meta, adapted)
    )
    return {
        "intent": prompt_meta["intent"],
        "kind": lp.kind(adapted),
        "ok": not violations,
        "accepted": bool((adapted.get("routing") or {}).get("accepted")),
        "flowHasWindowAnchor": _flow_has_window_anchor(adapted),
        "needsSelectionClass": lp.needs_selection_class(prompt_meta, adapted),
        "violations": violations,
        "facts": live_adapt.resolved_facts(adapted),
        "elapsed": elapsed,
        "model": body.get("model"),
        "source": _generator_source(envelope),
        "generatorReason": _generator_reason(envelope),
    }


def summarize(rows: list[dict]) -> dict:
    checked = [r for r in rows if r.get("ok") is not None and not r.get("error")]
    latencies = [float(r["elapsed"]) for r in rows if isinstance(r.get("elapsed"), (int, float))]
    return {
        "total": len(rows),
        "checked": len(checked),
        "passed": sum(1 for r in checked if r.get("ok") is True),
        "plannerErrors": sum(1 for r in rows if r.get("kind") == "planner-error"),
        "httpErrors": sum(1 for r in rows if r.get("error")),
        "accepted": sum(1 for r in checked if r.get("accepted")),
        "windowAnchorFlow": sum(1 for r in checked if r.get("flowHasWindowAnchor")),
        "needsSelectionUnjustified": sum(
            1 for r in checked if r.get("needsSelectionClass") == "unjustified"
        ),
        "heuristicFallback": sum(
            1 for r in checked if r.get("source") == "heuristic" and r.get("generatorReason")
        ),
        "latency": {
            "p50": _percentile(latencies, 0.50),
            "p90": _percentile(latencies, 0.90),
            "max": max(latencies) if latencies else None,
        },
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8194")
    ap.add_argument("--endpoint", default="/api/chat/ask")
    ap.add_argument("--targets", default="host")
    ap.add_argument("--discovery", default="node:lenovo")
    ap.add_argument("--execute", type=int, default=0)
    ap.add_argument("--model", default=None)
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--limit", type=int, default=3)
    ap.add_argument("--timeout", type=float, default=90.0)
    ap.add_argument("--delay", type=float, default=0.5)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    base_args = argparse.Namespace(prompts=None, anchor_only=True)
    prompts = live_run.prompt_corpus(base_args)
    if args.limit:
        prompts = prompts[: args.limit]
    targets = [t for t in args.targets.split(",") if t]
    base = args.base.rstrip("/")
    url = base + args.endpoint
    resolved_model = args.model or _model_from_env() or _model_from_server_config(base, args.timeout)
    if not args.json:
        print(f"model={resolved_model or '(none)'}")

    rows: list[dict] = []
    for run in range(args.runs):
        for idx, prompt_meta in enumerate(prompts):
            row = run_once(
                url=url,
                prompt_meta=prompt_meta,
                targets=targets,
                discovery=args.discovery,
                execute=args.execute,
                model=resolved_model,
                timeout=args.timeout,
            )
            row["run"] = run
            row["promptIndex"] = idx
            rows.append(row)
            if not args.json:
                mark = "✓" if row.get("ok") is True else ("⊘" if row.get("ok") is None else "✗")
                print(
                    f"{mark} run={run} prompt={idx} kind={row.get('kind') or 'error':16s} "
                    f"elapsed={row.get('elapsed', 0):6.2f}s anchor={row.get('flowHasWindowAnchor')} "
                    f"{prompt_meta['intent']}"
                )
                for violation in row.get("violations") or []:
                    print(f"      - {violation}")
            time.sleep(args.delay)

    summary = summarize(rows)
    payload = {"summary": summary, "cases": rows}
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        lat = summary["latency"]
        print(
            "\nRESULT: "
            f"{summary['passed']}/{summary['checked']} checked, "
            f"{summary['plannerErrors']} planner-error, {summary['httpErrors']} http-error, "
            f"accepted={summary['accepted']}, windowAnchorFlow={summary['windowAnchorFlow']}, "
            f"unjustifiedNeedsSelection={summary['needsSelectionUnjustified']}, "
            f"p50={lat['p50']:.2f}s p90={lat['p90']:.2f}s"
            if lat["p50"] is not None and lat["p90"] is not None
            else "\nRESULT: no completed requests"
        )
    return 0 if summary["checked"] > 0 and summary["passed"] == summary["checked"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
