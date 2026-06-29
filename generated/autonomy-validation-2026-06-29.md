# Walidacja automatyzacji i autonomii `testing/*`

Stan: 2026-06-29.

## Wynik

`testing/*` jako harness walidacyjny jest spójny i egzekwuje niezmienniki
autonomii. Pełny pytest po domknięciu Gen2/Gen7, dodaniu meta-bramy i
uwzględnieniu obecnych generacji:

```text
74 passed
```

Generator bazowy/offline:

```text
python3 run.py --json
108/108 passed
```

Generacje architektoniczne z runnerów:

```text
Gen2 data-flow:        6/6
Gen3 reversibility:   12/12
Gen4 state-router:     8/8
Gen5 cross-target:     9/9
Gen6 recall-adapt:     7/7
Gen7 effect-honesty:   9/9
```

## Nowa brama meta

Dodano `test_generation_contract.py`. Każda dostarczona generacja musi mieć:

- `expand()`, `check()`, `run_case()`;
- oracle, który przechodzi wszystkie własne przypadki;
- mutanta reprezentującego błędną architekturę;
- dowód, że checker łapie mutanta;
- standalone runner kończący się zielono.

To wymusza zasadę: test ma obalać konkretną błędną architekturę, nie tylko
potwierdzać happy path.

## Co działa poprawnie

- Gen2 łapie cichy default w data-flow (`monitor_from` bez źródła/dependency).
- Gen3 łapie fałszywą odwracalność i brak rollbacku po częściowej awarii.
- Gen4 łapie routing cache'owany na starym stanie twina.
- Gen5 łapie cichy fallback `node/service -> host`.
- Gen6 łapie literalny replay recall po zmianie fingerprintu/inwentarza.
- Gen7 łapie wnioskowanie destrukcyjności z sentymentu NL zamiast z kontraktu.
- Live smoke no-LLM przez lokalny chat nie łamie niezmienników dla sprawdzonych
  odpowiedzi:

```text
python3 live_run.py --execute 0 --no-llm --limit 12 --delay 0 --json
checked=11 passed=3 skipped=1
needsSelection=3 justified, 8 unjustified
```

Skip to `planner-error` dla jednej parafrazy, nie zaakceptowany błędny wynik.
Po dodaniu klasyfikacji `needs-selection` gołe screenshoty przy wielu monitorach
są poprawnymi pytaniami, a anchor „monitor z Chrome” bez rozwiązania przez
`window/query/list -> capture(monitor_from)` jest defektem autonomii.

## Dwie metryki real-adaptera

Real-adapter bez LLM ma teraz dwie osobne metryki:

```text
python3 run.py --real --json
fixture: 53/108 passed
portable: 53/86 checked, 22 planner-error skip
needsSelection: 24 justified, 33 unjustified
```

`fixture` porównuje wynik do syntetycznego `env_spec` i jest właściwą miarą dla
offline oracle. `portable` sprawdza tylko właściwości sensowne na bieżącym lub
realnie zasymulowanym środowisku: bramę, efekt, grounding, korelację
request/response, `needs-selection`, brak cichego defaultu i brak niespójnych
kopert. To jest właściwa metryka dla live/real, bo nie wymaga, żeby aktualna
maszyna odtwarzała każdą fixturę. `needs-selection` jest dalej dzielone na
uzasadnione i nieuzasadnione: autonomia to rozwiązać, gdy intencja + stan
wystarczają, i pytać, gdy nie wystarczają.

## Co jeszcze nie działa jako pełna autonomia

Strict fixture dla real-adaptera bez LLM nadal pokazuje luki zdolności:

Najważniejsze grupy porażek:

| Rodzina | Wynik | Wniosek |
|---|---:|---|
| `seed/paraphrase` | 0/9 | frazy typu „monitor, na którym jest Chrome” nie są autonomicznie rozwiązywane do wyniku |
| `relocate` | 0/9 | ten sam problem po zmianie stanu/inwentarza |
| `explicit` | 6/18 | część parafraz monitorów jawnych wpada w `needs-selection` albo `reject` |
| `scope-all` | 2/9 | „wszystkie monitory” nie jest stabilnie rozumiane |
| `conflict` | 2/9 | konflikt/all-scope nadal zależy od frazy |
| `oob` | 3/9 | część out-of-bounds kończy jako planner-error/needs-selection zamiast typed reject |

To potwierdza bieżącą diagnozę: sam checker i router-gate mają zęby, ale
realna ścieżka no-LLM nie ma pełnego pokrycia planowania nad `action_space +
twin_state`. Dla promptu „zrzut monitora, na którym jest Chrome”
oczekiwany kierunek to: `window/query/list(app=chrome)` -> `monitor_from` ->
`screen/query/capture`, a nie pytanie o wybór monitora, jeśli Chrome jest
jednoznacznie wykryty w inventory/window-list.

`/api/chat/config` zwraca niesekretny model (`LLM_MODEL`/`URIRUN_LLM_MODEL`), a
frontend pobiera go przed `/api/chat/ask` i wysyła w `model`. Model można podać
również jawnie: `python3 run.py --real --llm --model openrouter/model ...`.
Sekrety providera nadal muszą pochodzić ze środowiska procesu. Brak modelu to
blokada providera, nie wynik bramy akceptacji.

Live smoke LLM po restarcie dashboardu z `openrouter/google/gemini-3.5-flash`
pokazał `1/3 checked` dla anchorów: jedna fraza dała poprawny wynik
`monitor=2 · output=DP-2 · scope=monitor · 2160x3840`, dwie nadal wróciły jako
`needs-selection-unjustified`. Wykonanie `execute=true` dla pierwszej frazy
wygenerowało artefakt DP-2/4K:
`/home/tom/.urirun/artifacts/screenshots/urirun-kvm-shot-1680644.png`.

## Kolejne domknięcia

1. Wpiąć realny `twin://host/env/query/inventory` i domeny env-enum jako wejście
   do plannera/routera w torze live/no-LLM.
2. Przenieść rozstrzyganie anchorów typu „monitor z Chrome” do deklaratywnej
   warstwy routera/data-flow, nie do heurystyk chatu.
3. Ujednolicić typed reject dla monitorów spoza inwentarza: `monitor-not-in-inventory`,
   nie `planner-error`.
4. Po ustawieniu `URIRUN_LLM_MODEL`/`LLM_MODEL` albo podaniu `--model` mierzyć
   `--real --llm` jako rozkład coverage po wielu przebiegach: brama musi mieć
   100% na checked, planowanie ma rosnąć statystycznie, nie przez dopisywanie
   heurystyk pod 108 fraz.
