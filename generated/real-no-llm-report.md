# Real no-LLM metamorphic report

- total: 108
- passed: 53
- failed: 55

| family | passed | total | sample failures |
|---|---:|---:|---|
| ambiguous | 8 | 9 | ambiguous#04: kind: expected needs-selection got reject |
| conflict | 2 | 9 | conflict-all-plus-2#01: kind: expected result got needs-selection<br>conflict-all-plus-2#02: kind: expected result got reject |
| explicit | 6 | 18 | explicit-2#02: kind: expected result got reject<br>explicit-2#03: kind: expected result got needs-selection |
| no-anchor | 8 | 9 | anchor-closed#07: kind: expected needs-selection got reject |
| oob | 3 | 9 | oob-9#02: reject: reason mismatch, want monitor-not-in-inventory, got ['planner-error']<br>oob-9#03: kind: expected reject got needs-selection |
| relocate | 0 | 9 | anchor-relocate#00: kind: expected result got needs-selection<br>anchor-relocate#01: kind: expected result got needs-selection |
| remember | 8 | 9 | remembered-2#04: kind: expected result got reject |
| remember/fp-guard | 8 | 9 | fp-guard#04: kind: expected needs-selection got reject |
| scope-all | 2 | 9 | scope-all#01: kind: expected result got needs-selection<br>scope-all#02: kind: expected result got reject |
| seed/paraphrase | 0 | 9 | anchor-3mon#00: kind: expected result got needs-selection<br>anchor-3mon#01: kind: expected result got needs-selection |
| shrink | 8 | 9 | sole-1mon#04: kind: expected result got reject |
