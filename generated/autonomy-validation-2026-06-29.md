# Walidacja automatyzacji i autonomii `testing/*`

Stan: 2026-06-29.

## Wynik

`testing/*` jako harness walidacyjny jest spójny i egzekwuje niezmienniki
autonomii. Pełny pytest po domknięciu kolejnych generacji, dodaniu meta-bramy i
uwzględnieniu regresji live:

```text
98 passed, 1 xfailed
```

Generator bazowy/offline:

```text
python3 run.py --json
108/108 passed
```

Generacje architektoniczne z runnerów:

```text
Gen2 data-flow:        8/8
Gen3 reversibility:   12/12
Gen4 state-router:     9/9
Gen5 cross-target:     9/9
Gen6 recall-adapt:     7/7
Gen7 effect-honesty:   9/9
Gen8 verification:     5/5
Gen9 preferences:      6/6
Gen10 idempotence:     4/4
meta ladder:           9/9
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
- Gen8 łapie `ok:true` bez realnej weryfikacji świata.
- Gen9 łapie preferencje, które nie są kluczowane fingerprintem środowiska.
- Gen10 łapie ślepe ponowienie mutacji i duplikaty operacji wykonawczych.
- Live checker łapie teraz także zdublowany `window/command/focus` w flow.
- Live checker łapie przeciek efektu w preview: `execute=false` + screenshot/artifact
  evidence (`path`, `artifactPath`, `pngbase64`) kończy jako `dry-run-effect`.
- Live smoke no-LLM przez lokalny chat nie łamie niezmienników dla sprawdzonych
  odpowiedzi i nie wykonuje screenshotów w `execute=false`:

```text
anchor Chrome:   ok, window/query/list -> focus -> capture(monitor_from), 0 screenshotów w preview
generic shot:    justified needs-selection, 0 screenshotów w preview
explicit-2:      ok, typed monitor=2, 0 screenshotów w preview
all monitors:    ok, typed scope=all, 0 screenshotów w preview
monitor 99:      env-domain-invalid, allowed=[1,2,3], 0 screenshotów w preview
```

Po dodaniu plannerowego inventory/window-list gołe screenshoty przy wielu
monitorach są poprawnymi pytaniami, a anchor „monitor z Chrome” przechodzi przez
`window/query/list -> capture(monitor_from)`.

## Dwie metryki real-adaptera

Real-adapter bez LLM ma teraz dwie osobne metryki:

```text
python3 run.py --real --portable
fixture: 108/108 passed
portable: 108/108 checked, 0 planner-error skip
needsSelection: 27 justified, 0 unjustified
```

`fixture` porównuje wynik do syntetycznego `env_spec` i jest właściwą miarą dla
offline oracle. `portable` sprawdza tylko właściwości sensowne na bieżącym lub
realnie zasymulowanym środowisku: bramę, efekt, grounding, korelację
request/response, `needs-selection`, brak cichego defaultu i brak niespójnych
kopert. To jest właściwa metryka dla live/real, bo nie wymaga, żeby aktualna
maszyna odtwarzała każdą fixturę. `needs-selection` jest dalej dzielone na
uzasadnione i nieuzasadnione: autonomia to rozwiązać, gdy intencja + stan
wystarczają, i pytać, gdy nie wystarczają. To nadal jest liczba matrycy, nie
dowód pokrycia całej przestrzeni intencji.

## Probe poza matrycą

Dodano `ood_anchor_probe.py`, który mierzy frazy spoza 108-case korpusu. Aktualny
no-LLM wynik:

```text
python3 ood_anchor_probe.py
required OOD anchors: 1/2
VS Code:   window/query/list -> capture(monitor_from) działa
terminal:  brak window-anchor flow
known-gap: relacja przestrzenna "obok terminala", deskryptor "duży monitor"
```

Interpretacja: no-LLM generalizuje już część app-anchorów z live window inventory,
ale `27 justified / 0 unjustified` nie oznacza pełnej autonomii. Migrację z leksyki
do deklaratywnego/LLM planowania należy bramkować właśnie takimi OOD rodzinami.

## Co jeszcze nie działa jako pełna autonomia

Funkcjonalne invarianty `testing/*` są zielone, ale live HTTP sweep jest za wolny
jako codzienna brama. Pełny `testing/live_run.py --execute 0 --no-llm` został
przerwany po kilku minutach, bo każdy prompt pobiera pełne
profile/surface/window/browserSessions. To jest bottleneck warstwy środowiska,
nie aktualna porażka predykatu akceptacji.

Gen4 został rozszerzony o cache inventory: ciężki inventory można cache'ować tylko
pod tanim live fingerprintem. Cache po sesji/czasie, który przepuszcza stary
monitor po zmianie fingerprintu, jest łapany jako `stale-inventory-cache`.

Druga luka jest architektoniczna: no-LLM nadal zawiera leksykalne fallbacki
(`_SCREENSHOT_KWS`, `_ALL_MONITOR_KWS`, wzorce monitorów) w `urirun_flow`.
Po tej turze są objęte testami, ale docelowo powinny zostać zastąpione
deklaratywnymi slotami/intencjami z kontraktów i action_space albo LLM plannerem
walidowanym tą samą bramą.

`/api/chat/config` zwraca niesekretny model (`LLM_MODEL`/`URIRUN_LLM_MODEL`), a
frontend pobiera go przed `/api/chat/ask` i wysyła w `model`. Model można podać
również jawnie: `python3 run.py --real --llm --model openrouter/model ...`.
Sekrety providera nadal muszą pochodzić ze środowiska procesu. Brak modelu to
blokada providera, nie wynik bramy akceptacji.

Nowy pomiar live LLM:

```text
python3 llm_anchor_distribution.py --runs 1 --limit 1 --json
checked=1 passed=1 accepted=1 windowAnchorFlow=1 heuristicFallback=1 p50=6.12s
model=openrouter/google/gemini-3.5-flash
generatorReason=OpenRouter key limit exceeded
```

Interpretacja: request poprawnie pobiera model z `/api/chat/config` i wysyła go
w body z `noLlm=false`, ale provider jest obecnie zablokowany limitem klucza, więc
system degraduje do heurystyki. To jest poprawne zachowanie fallbacku i zielony
wynik bramy, ale nadal **nie** jest pomiarem jakości toru LLM. Do decyzji o
odwróceniu domyślnego planera potrzebny jest przebieg bez `heuristicFallback`.

Aktualne wykonanie `execute=true` dla anchora Chrome wygenerowało artefakt DP-2/4K:
`/home/tom/.urirun/artifacts/screenshots/urirun-kvm-shot-2105438.png`.

## Kolejne domknięcia

1. Dodać cache/budżet czasowy dla plannerowego inventory: osobno szybkie
   `window/query/list`, osobno cięższe browser/session profile, kluczowane
   fingerprintem środowiska.
2. Wyciągnąć leksykalne fallbacki no-LLM do deklaratywnej warstwy slotów/intencji
   opartej o kontrakty URI; kod ma interpretować deklarację, nie zawierać list fraz.
3. Przenieść acquisition `planner_environments` z helpera chatu/flow do jawnego
   URI `twin://host/env/query/inventory` jako jednego read-only kontraktu.
4. Po ustawieniu `URIRUN_LLM_MODEL`/`LLM_MODEL` albo podaniu `--model` mierzyć
   `--real --llm` jako rozkład coverage po wielu przebiegach: brama musi mieć
   100% na checked, planowanie ma rosnąć statystycznie, nie przez dopisywanie
   heurystyk pod 108 fraz.
