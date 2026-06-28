"""Seed -> 100+ branched NL cases by metamorphic relations.

One seed (the live chrome-monitor trace) is expanded along axes, each axis a
metamorphic relation with a KNOWN effect on the expected properties:

  paraphrase  same intent, same env        -> properties unchanged
  relocate    chrome on a different monitor -> captured monitor follows chrome
  shrink      one monitor only             -> sole-option resolution, no asking
  explicit    user names a monitor          -> that monitor, regardless of chrome
  scope-all   "all monitors"               -> skipWhen, no single monitor
  remember    preference set for fingerprint-> remembered monitor (no anchor)
  fp-guard    preference NOT for this fp    -> must NOT leak -> needs-selection
  ambiguous   N monitors, nothing to go on  -> typed needs-selection
  oob         monitor not in inventory      -> reject (grounding)
  no-anchor   chrome window closed          -> needs-selection (graceful)
  conflict    "all" + explicit monitor      -> defined precedence (scope wins)

Each case carries `expect` (the property bundle), not an expected flow.
"""
from __future__ import annotations

# 3-monitor fixture, matching the live trace (HDMI-1 primary, DP-2, DP-1) ------
MON3 = [
    {"id": 1, "connector": "HDMI-1", "primary": True},
    {"id": 2, "connector": "DP-2"},
    {"id": 3, "connector": "DP-1"},
]
MON1 = [{"id": 1, "connector": "HDMI-1", "primary": True}]

# --- NL paraphrase pools (Polish, the user's language; a couple of EN) ---------
ANCHOR = [
    "zrób zrzut ekranu monitora, na którym jest chrome",
    "screenshot tego monitora gdzie mam otwartego chrome",
    "przechwyć ekran z przeglądarką chrome",
    "zrzut monitora z chrome",
    "zrób screena tego ekranu gdzie jest google chrome",
    "capture the monitor showing chrome",
    "pokaż zrzut ekranu z chrome",
    "zrzutuj monitor na którym wyświetla się chrome",
    "zrób fotkę ekranu z otwartym chrome",
]
GENERIC = [
    "zrób zrzut ekranu",
    "zrzut ekranu",
    "screenshot",
    "przechwyć ekran",
    "zrób screena",
    "pokaż zrzut ekranu",
    "zrzutuj ekran",
    "zrób print screen",
    "capture the screen",
]
EXPLICIT = [
    "zrób zrzut monitora {n}",
    "screenshot monitora {n}",
    "przechwyć monitor numer {n}",
    "zrzut ekranu {n}",
    "zrób screena monitora {n}",
    "pokaż zrzut monitora {n}",
    "zrzutuj monitor {n}",
    "capture monitor {n}",
    "ekran {n} zrzut",
]
ALL = [
    "zrób zrzut wszystkich monitorów",
    "screenshot wszystkich ekranów",
    "przechwyć wszystkie monitory",
    "zrzut całego pulpitu",
    "zrób screena wszystkich ekranów",
    "pokaż wszystkie monitory",
    "zrzutuj cały desktop",
    "capture all monitors",
    "wszystkie ekrany zrzut",
]

# --- families: (id, MR tag, phrasing pool, plan_hint, env_spec, expect) --------
FAMILIES = [
    # seed + paraphrase: chrome anchored, 3 monitors, chrome on #3
    {"id": "anchor-3mon", "mr": "seed/paraphrase", "pool": ANCHOR,
     "plan_hint": {"anchor": "chrome", "scope": None, "monitor": None},
     "env_spec": {"monitors": MON3, "chrome_on_monitor": 3, "cdp": True},
     "expect": {"kind": "result", "monitor": "chrome", "scope": "monitor"}},

    # relocate: chrome on #2 -> captured monitor must follow
    {"id": "anchor-relocate", "mr": "relocate", "pool": ANCHOR,
     "plan_hint": {"anchor": "chrome", "scope": None, "monitor": None},
     "env_spec": {"monitors": MON3, "chrome_on_monitor": 2, "cdp": True},
     "expect": {"kind": "result", "monitor": "chrome", "scope": "monitor"}},

    # shrink: one monitor, no anchor -> sole-option resolution
    {"id": "sole-1mon", "mr": "shrink", "pool": GENERIC,
     "plan_hint": {"anchor": None, "scope": None, "monitor": None},
     "env_spec": {"monitors": MON1, "chrome_on_monitor": 1, "cdp": True},
     "expect": {"kind": "result", "monitor": 1, "scope": "monitor"}},

    # explicit monitor 2
    {"id": "explicit-2", "mr": "explicit", "pool": EXPLICIT, "fmt": {"n": 2},
     "plan_hint": {"anchor": None, "scope": None, "monitor": 2},
     "env_spec": {"monitors": MON3, "chrome_on_monitor": 3, "cdp": True},
     "expect": {"kind": "result", "monitor": 2, "scope": "monitor"}},

    # explicit primary monitor 1
    {"id": "explicit-1", "mr": "explicit", "pool": EXPLICIT, "fmt": {"n": 1},
     "plan_hint": {"anchor": None, "scope": None, "monitor": 1},
     "env_spec": {"monitors": MON3, "chrome_on_monitor": 3, "cdp": True},
     "expect": {"kind": "result", "monitor": 1, "scope": "monitor"}},

    # scope-all -> skipWhen, capture all
    {"id": "scope-all", "mr": "scope-all", "pool": ALL,
     "plan_hint": {"anchor": None, "scope": "all", "monitor": None},
     "env_spec": {"monitors": MON3, "chrome_on_monitor": 3, "cdp": True},
     "expect": {"kind": "result", "monitor": None, "scope": "all"}},

    # remembered preference (#2) for this fingerprint, no anchor
    {"id": "remembered-2", "mr": "remember", "pool": GENERIC,
     "plan_hint": {"anchor": None, "scope": None, "monitor": None},
     "env_spec": {"monitors": MON3, "chrome_on_monitor": 3, "cdp": True, "preference": 2},
     "expect": {"kind": "result", "monitor": 2, "scope": "monitor"}},

    # fingerprint guard: preference NOT set for this fp -> must not leak
    {"id": "fp-guard", "mr": "remember/fp-guard", "pool": GENERIC,
     "plan_hint": {"anchor": None, "scope": None, "monitor": None},
     "env_spec": {"monitors": MON3, "chrome_on_monitor": 3, "cdp": True,
                  "preference": None, "fingerprint": "env-OTHER-99"},
     "expect": {"kind": "needs-selection"}},

    # ambiguous: N monitors, nothing to disambiguate
    {"id": "ambiguous", "mr": "ambiguous", "pool": GENERIC,
     "plan_hint": {"anchor": None, "scope": None, "monitor": None},
     "env_spec": {"monitors": MON3, "chrome_on_monitor": 3, "cdp": True},
     "expect": {"kind": "needs-selection"}},

    # out-of-bounds explicit monitor 9 -> reject (inventory grounding)
    {"id": "oob-9", "mr": "oob", "pool": EXPLICIT, "fmt": {"n": 9},
     "plan_hint": {"anchor": None, "scope": None, "monitor": 9},
     "env_spec": {"monitors": MON3, "chrome_on_monitor": 3, "cdp": True},
     "expect": {"kind": "reject", "reason": "monitor-not-in-inventory"}},

    # missing anchor: chrome window closed -> graceful needs-selection
    {"id": "anchor-closed", "mr": "no-anchor", "pool": ANCHOR,
     "plan_hint": {"anchor": "chrome", "scope": None, "monitor": None},
     "env_spec": {"monitors": MON3, "chrome_on_monitor": None, "cdp": True},
     "expect": {"kind": "needs-selection"}},

    # conflict: "all" + explicit monitor -> defined precedence (scope wins)
    {"id": "conflict-all-plus-2", "mr": "conflict", "pool": ALL,
     "plan_hint": {"anchor": None, "scope": "all", "monitor": 2},
     "env_spec": {"monitors": MON3, "chrome_on_monitor": 3, "cdp": True},
     "expect": {"kind": "result", "monitor": None, "scope": "all"}},
]


def expand() -> list[dict]:
    """Fan the families across their paraphrase pools into the full corpus."""
    cases: list[dict] = []
    for fam in FAMILIES:
        fmt = fam.get("fmt", {})
        for i, tmpl in enumerate(fam["pool"]):
            cases.append({
                "id": f"{fam['id']}#{i:02d}",
                "intent": tmpl.format(**fmt),
                "mr": fam["mr"],
                "plan_hint": fam["plan_hint"],
                "env_spec": fam["env_spec"],
                "expect": fam["expect"],
            })
    return cases
