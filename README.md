# nlmatrix — od jednego przykładu NL do 100 rozgałęzionych, testujących twin + rejestr

Masz ręczne przykłady (jak żywy ślad zrzutu chrome) i katalog `examples/*`. Ten
moduł zamienia **jeden** taki przykład w **100+** rozgałęzionych przykładów NL i
sprawdza je nie pod kątem „czy powstał dokładnie ten flow", tylko **czy zachodzą
niezmienniki** — bo to jedyne, co skaluje się do setek przypadków i jest zgodne z
tezą projektu: *brama akceptacji jest uniwersalnym predykatem, nie drzewem*.

## Zasada: niezmienniki, nie przepływy

Nie da się ręcznie wypisać 100 oczekiwanych flow, a planner (recall/LLM) ma prawo
wariować. Więc każdy wariant niesie **właściwości**, które muszą zachodzić
niezależnie od sformułowania planu. To **testowanie metamorficzne**: nie
potrzebujesz znanego-dobrego wyjścia dla każdego wejścia, tylko relacji „jak zmiana
wejścia zmienia właściwości wyjścia".

```
jeden seed (żywy ślad)
  └─ transformacje metamorficzne ─→ 108 przypadków NL
        każdy = { intent (NL), env (stan twina), expect (właściwości) }
  └─ wykonanie: plan(intent, twin_state, action_space) → router accept → execute
  └─ sprawdzenie: niezmienniki + oczekiwanie wariantu
```

## Niezmienniki (to są „subtelności", które łapiemy)

Wyciągnięte wprost ze struktury żywej koperty:

1. **Brama**: `accepted == true` ⟺ zero `blockedSteps` i zero `violations`.
2. **Uczciwość efektu**: `step.effect` == zadeklarowany `contract.effect`
   (dokładnie klasa błędu `is_destructive` — heurystyka musi zgadzać się z
   deklaracją albo z niej wynikać); trasa `query` musi być oznaczona `safe`.
3. **Ugruntowanie w inwentarzu**: przechwycony monitor ∈
   `inventory.domains["env:monitors.id"]`. Nie da się złapać monitora 9, gdy są 1–3.
4. **Rozwiązanie env-enum**: kolejność jawny → data-flow → jedyny → zapamiętany →
   `needs-selection`. **Nigdy** ciche `monitor=0` przy niejednoznaczności.
5. **Kluczowanie fingerprintem**: zapamiętana preferencja nie przecieka między
   fingerprintami (inny fingerprint → musi pytać, nie użyć starej preferencji).
6. **Spójność data-flow**: `monitor_from: "X.result…"` wymaga kroku `X` w
   `depends_on`, poprzedzającego.

## Osie metamorficzne (jak jeden seed się rozgałęzia)

| Oś | Co zmienia | Oczekiwany skutek |
|---|---|---|
| `paraphrase` | tylko słowa, ten sam env | właściwości bez zmian (test krawędzi intencja→epizod) |
| `relocate` | chrome na innym monitorze | przechwycony monitor podąża za chrome |
| `shrink` | jeden monitor | rozwiązanie „jedyny", bez pytania |
| `explicit` | user podaje monitor | ten monitor, niezależnie od chrome |
| `scope-all` | „wszystkie monitory" | `skipWhen`, brak pojedynczego monitora |
| `remember` | preferencja dla fingerprintu | zapamiętany monitor (bez kotwicy) |
| `fp-guard` | preferencja **nie** dla tego fp | nie przecieka → `needs-selection` |
| `ambiguous` | N monitorów, brak przesłanek | typed `needs-selection` |
| `oob` | monitor spoza inwentarza | `reject` (ugruntowanie) |
| `no-anchor` | okno chrome zamknięte | łagodne `needs-selection` |
| `conflict` | „wszystkie" + jawny monitor | zdefiniowane pierwszeństwo (scope wygrywa) |

Te same słowa pod innym stanem twina niosą inny poprawny wynik — to celowe (np.
fraza o chrome jest `result` przy otwartym chrome i `needs-selection` przy
zamkniętym). To jest sedno: testujesz **funkcję stanu**, nie sztywny skrypt.

## Uruchomienie

```bash
python3 run.py --list      # wypisz wszystkie wygenerowane linie NL (jeden pod drugim)
python3 run.py             # wykonaj + sprawdź niezmienniki, raport per rodzina
python3 run.py --json      # wynik maszynowy
python3 run.py --mr relocate   # tylko jedna rodzina metamorficzna
python3 -m pytest test_nlmatrix.py -q
```

Domyślny wykonawca to **oracle referencyjny** (`twin_registry_sim.py`) — koduje
poprawne zachowanie. Jego rola: (a) udowodnić, że generator i checker są spójne
end-to-end, (b) zdefiniować zachowanie, względem którego mierzysz prawdziwy system.
`test_nlmatrix.py` karmi checker **celowo zepsutymi kopertami** (monitor spoza
inwentarza, efekt-kłamstwo, ciche `monitor=0`, przeciek preferencji) i sprawdza, że
checker je **łapie** — bo checker, który nigdy nie pada, jest bezużyteczny.

## Wpięcie prawdziwego systemu

`run.py --real` jest podpięty do prawdziwych modułów:

- `urirun_flow.flow_planner.make_flow`,
- `urirun_flow.env_selection.resolve_env_enums`,
- `urirun_connector_router.routing.accept_plan`.

Tryb jest niedestrukcyjny: używa syntetycznego stanu twina z `env_spec`, wykonuje
realne planowanie/rozstrzyganie, ale końcowy screenshot symuluje z tej kontrolowanej
fixtury zamiast dotykać KVM.

```bash
python3 run.py --real          # realny planner no-LLM + real router/env-selection
python3 run.py --real --portable  # licz tylko live-safe invariants; fixture osobno
python3 run.py --real --llm    # realny LLM planner, jeśli URIRUN_LLM_MODEL/LLM_MODEL jest ustawiony
python3 run.py --real --llm --model openrouter/model  # model jawnie w requestcie testowym
```

Dwa tryby plannera:

- **deterministyczny oracle** — referencja, co produkuje zdolny planner;
- **real** — to, co stress-testujesz. Wariant, w którym planner mis-planuje,
  wychodzi jako naruszenie właściwości, **nie** po cichu „zaliczony".

Stan na 2026-06-29 po podłączeniu plannerowego inventory/window-list do dry-run
i po naprawie lokalnego dispatchu:

- **fixture oracle:** `108/108`;
- **portable/live-safe:** `108/108 checked`, `0 planner-error skip`;
- **needs-selection:** `27 justified`, `0 unjustified`.

To oznacza, że realny no-LLM tor planowania/rozstrzygania przechodzi wszystkie
metamorficzne właściwości na kontrolowanym stanie twina. „Goły screenshot" przy
wielu monitorach nadal poprawnie pyta, ale anchor „monitor z Chrome" przechodzi
przez `window/query/list -> screen/query/capture(monitor_from)`, jawny monitor
jest typed value, `scope=all` jest typed scope, a monitor spoza domeny kończy jako
`env-domain-invalid` z listą dozwolonych wartości, nie jako pusta karta wyboru.

Live HTTP przez dashboard jest osobnym pomiarem wydajnościowo-operacyjnym. Smoke
na `execute=false` dla pięciu klas (`anchor`, `generic`, `explicit-2`, `all`,
`oob`) potwierdził poprawne koperty i brak screenshotów w preview. Pełny
`testing/live_run.py --execute 0 --no-llm` jest obecnie za wolny jako brama
interaktywna, bo każdy prompt odpyta pełne profile/surface/window/browserSessions.
Ten tor wymaga cache/budżetu czasowego dla `twin://host/env/query/inventory`.

Stan `--real --llm` wymaga skonfigurowanego providera. Model można podać przez
`URIRUN_LLM_MODEL`/`LLM_MODEL` albo jawnie przez `--model`; dashboard dodatkowo
eksponuje niesekretny `/api/chat/config`, a frontend pobiera go przed requestem.
Sekrety providera (np. API key) nadal muszą być w środowisku procesu. Brak modelu
jest raportowany jako `planner-error` skip — to precondition providera, nie
zielony ani czerwony wynik architektury.

## Pomiar toru LLM jako rozkładu

Pojedynczy zielony ślad z anchorem Chrome jest dobrym dowodem kierunku, ale nie
jest miarą produkcyjną. Do tego służy:

```bash
python3 llm_anchor_distribution.py --runs 3 --limit 3
python3 llm_anchor_distribution.py --runs 5 --model openrouter/model --json
```

Runner wysyła anchor-prompty do live chatu z `no_llm=false`, przed zbudowaniem
requestu pobiera model z `URIRUN_LLM_MODEL`, potem `LLM_MODEL`, a gdy ich nie ma
z niesekretnego `/api/chat/config` (chyba że podasz `--model`) i mierzy: ile planów
przeszło live-invariants, ile miało `window/query/list -> capture(monitor_from)`,
ile było `planner-error`, ile razy tor spadł do heurystyki z powodu providera
(`heuristicFallback` + `generatorReason`), oraz p50/p90 latencji. To jest właściwy
próg do decyzji, czy LLM prowadzi domyślny tor:
brama pozostaje twarda, ale planowanie mierzymy jako rozkład.

## Atestacje warstwowe

`layer_attestations.py` i `test_attestations.py` pilnują, żeby anomalia była
przypisana do właściwej warstwy. Przykład DP-2/DP-1 jest celowo redundantny:
samospójność w dół (`captured == selected`) przepuszcza błąd, więc L8 inventory
musi być weryfikowane niezależnie przez `monitorConnector` i geometrię okna.

```bash
python3 -m pytest test_attestations.py -q
```

Po restarcie dashboardu `execute=true` dla
`zrób zrzut jednego ekranu monitora, na którym jest przeglądarka chrome`
wygenerował zrzut z DP-2/AOC 4K przez data-flow z inventory:
`window/query/list(app=chrome) -> window/command/focus -> screen/query/capture`.
Artefakt miał `monitor=2`, `outputConnector=DP-2`, `scope=monitor`.

## Domknięcie pętli

Ten korpus nie jest jednorazowy. Zweryfikowane warianty (te, które przeszły
niezmienniki) to **known-good epizody** — paliwo dla indeksu z
`EXPERIENCE_RETRIEVAL.md`. Ta sama weryfikacja, która dowodzi poprawności wariantu,
czyni jego rozwiązanie wyszukiwalnym. A że **każdy** wariant przechodzi przez tę
samą bramę akceptacji — korpus jest dowodem, że brama jest uniwersalna, nie że
masz 100 gałęzi `if`.

Linia bez zmian: LLM proponuje plany, nie bramy; testujesz predykat akceptacji, nie
ścieżkę. Gdyby asercje były „NL → dokładnie ten flow", po pierwszej zmianie
plannera korpus zacząłby kłamać — dlatego trzymamy go na niezmiennikach.
