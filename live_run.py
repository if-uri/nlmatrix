#!/usr/bin/env python3
"""Drive N NL prompts at the LIVE urirun chat over HTTP and check invariants.

You cannot inject a twin fixture over HTTP, so this asserts (a) env-INDEPENDENT
invariants and (b) self-consistency read from each response, and RECORDS the
resolved facts. Fixture-controlled absolute expectations live in the offline
oracle (run.py).

  # 1) verify the request shape against ONE real submit first:
  python3 live_run.py --show-request
  #    (open the dashboard, submit one chat, copy the POST path/body from the
  #     browser Network tab, then set --endpoint / edit build_body if needed)

  # 2) bulk logic run, no side effects, throttled:
  python3 live_run.py --execute 0 --delay 0.3
  python3 live_run.py --execute 0 --model openrouter/model --delay 0.3

  # 3) end-to-end subset that actually captures (slower, throttle harder):
  python3 live_run.py --anchor-only --execute 1 --delay 1.0

  python3 live_run.py --prompts my_prompts.txt    # your own list, one per line
  python3 live_run.py --json                        # machine-readable
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

import live_adapt
import live_properties as lp
import transforms

# which family ids map to which live-checkable phrasing
_PHRASING = {
    "anchor-3mon": "anchor", "anchor-relocate": "anchor", "anchor-closed": "anchor",
    "explicit-2": "explicit", "explicit-1": "explicit", "oob-9": "explicit",
    "scope-all": "all", "conflict-all-plus-2": "all",
}


def prompt_corpus(args) -> list[dict]:
    if args.prompts:
        with open(args.prompts, encoding="utf-8") as fh:
            return [{"intent": l.strip(), "phrasing": "custom"} for l in fh if l.strip()]
    out: list[dict] = []
    for fam in transforms.FAMILIES:
        if args.anchor_only and "anchor" not in fam["id"]:
            continue
        phr = _PHRASING.get(fam["id"], "generic")
        n = fam.get("fmt", {}).get("n")
        for tmpl in fam["pool"]:
            out.append({"intent": tmpl.format(**fam.get("fmt", {})), "phrasing": phr, "monitor": n})
    # de-dup identical NL (live env is fixed, so identical words run once)
    seen, uniq = set(), []
    for p in out:
        if p["intent"] not in seen:
            seen.add(p["intent"])
            uniq.append(p)
    return uniq


def build_body(prompt: str, targets: list[str], execute: int, discovery: str,
               no_llm: bool = False, model: str | None = None) -> dict:
    """The chat POST body. VERIFY this against a real submit — field names may
    differ in your build (e.g. 'selectedTargets' vs 'targets')."""
    body = {
        "prompt": prompt,
        "targets": targets,
        "target_explicit": True,
        "execute": bool(execute),
        "action": "chat:run",
        "no_llm": bool(no_llm),
    }
    if model and not no_llm:
        body["model"] = model
    if discovery:
        body["discovery"] = discovery
    return body


def post_json(url: str, body: dict, timeout: float) -> dict:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8194")
    ap.add_argument("--endpoint", default="/api/chat/ask",
                    help="chat POST path — VERIFY against a real submit in devtools")
    ap.add_argument("--targets", default="host")
    ap.add_argument("--discovery", default="node:lenovo")
    ap.add_argument("--execute", type=int, default=0, help="0=plan+route only, 1=run side effects")
    ap.add_argument("--no-llm", action="store_true", help="send no_llm=true to the chat API")
    ap.add_argument("--model", default=None, help="send model in the chat request body")
    ap.add_argument("--delay", type=float, default=0.3, help="throttle between prompts (s)")
    ap.add_argument("--timeout", type=float, default=60.0)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--anchor-only", action="store_true")
    ap.add_argument("--prompts", default=None)
    ap.add_argument("--show-request", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    cases = prompt_corpus(args)
    if args.limit:
        cases = cases[: args.limit]
    targets = [t for t in args.targets.split(",") if t]
    url = args.base.rstrip("/") + args.endpoint

    if args.show_request:
        body = build_body(cases[0]["intent"], targets, args.execute, args.discovery, args.no_llm, args.model)
        print("POST", url)
        print(json.dumps(body, ensure_ascii=False, indent=2))
        print(f"\n# {len(cases)} prompts queued. Verify path+body against one real "
              f"submit, then drop --show-request.", file=sys.stderr)
        return 0

    results, passed, skipped = [], 0, 0
    ns_justified, ns_unjustified = 0, 0
    for i, c in enumerate(cases):
        body = build_body(c["intent"], targets, args.execute, args.discovery, args.no_llm, args.model)
        try:
            envelope = post_json(url, body, args.timeout)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError) as e:
            print(f"✗ [{i:03d}] HTTP/parse error: {e}  ({c['intent']})", file=sys.stderr)
            results.append({"intent": c["intent"], "ok": False, "error": str(e)})
            time.sleep(args.delay)
            continue
        a = live_adapt.adapt(envelope)
        if lp.kind(a) == "planner-error":
            # The chat never produced a plan (LLM down / rate-limited, fallback disabled).
            # Record as an infra skip — counting it as a passing "reject" would green-wash an outage.
            skipped += 1
            results.append({"intent": c["intent"], "kind": "planner-error", "ok": None,
                            "skipped": "planner-error", "error_message": a.get("error_message")})
            if not args.json:
                print(f"⊘ [{i:03d}] planner-error  {(a.get('error_message') or '')[:46]:46s} {c['intent']}")
            time.sleep(args.delay)
            continue
        viol = (lp.check_invariants(a) + lp.check_self_consistency(a)
                + lp.expected_from_prompt(c, a)
                + lp.check_correlation(c, a, args.no_llm)
                + lp.check_needs_selection_autonomy(c, a))
        ok = not viol
        passed += ok
        ns_cls = lp.needs_selection_class(c, a)
        if ns_cls == "justified":
            ns_justified += 1
        elif ns_cls == "unjustified":
            ns_unjustified += 1
        facts = live_adapt.resolved_facts(a)
        results.append({"intent": c["intent"], "kind": lp.kind(a), "facts": facts,
                        "ok": ok, "violations": viol, "needsSelectionClass": ns_cls})
        if not args.json:
            ns_tag = f" [{ns_cls}]" if ns_cls else ""
            mark = "✓" if ok else "✗"
            print(f"{mark} [{i:03d}] {lp.kind(a):14s} {facts:46s} {c['intent']}{ns_tag}")
            for x in viol:
                print(f"        - {x}")
        time.sleep(args.delay)

    checked = len(results) - skipped
    if args.json:
        print(json.dumps({"total": len(results), "checked": checked, "passed": passed,
                          "skipped": skipped,
                          "needsSelection": {
                              "justified": ns_justified,
                              "unjustified": ns_unjustified,
                          },
                          "cases": results}, ensure_ascii=False, indent=2))
    else:
        note = f"; {skipped} skipped (planner/infra error — LLM down?)" if skipped else ""
        print(f"\nRESULT: {passed}/{checked} checked prompts satisfy all live invariants "
              f"(execute={args.execute}){note}")
        if ns_justified or ns_unjustified:
            print(f"needs-selection: {ns_justified} justified (correct to ask) · "
                  f"{ns_unjustified} UNJUSTIFIED (intent had an anchor — autonomy gap, drive to 0 "
                  f"via the LLM planner, not anchor heuristics)")
    # Green only when something was actually checked and all checks held.
    return 0 if (checked > 0 and passed == checked) else 1


if __name__ == "__main__":
    raise SystemExit(main())
