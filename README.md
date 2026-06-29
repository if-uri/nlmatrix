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

Stan na 2026-06-29 dla realnego no-LLM toru ma dwie liczby:

- **fixture oracle:** `53/108` — strict porównanie do syntetycznego `env_spec`;
- **portable/live-safe:** `53/86 checked`, `22 planner-error skip` — brama,
  grounding, efekt, korelacja request/response, brak cichego defaultu i
  klasyfikacja `needs-selection`.
- **needs-selection:** `24 justified`, `33 unjustified` — goły screenshot przy
  wielu monitorach może pytać; „monitor z Chrome”, jawny monitor albo `scope=all`
  nie powinny pytać, tylko rozwiązać/rejectować przez action_space + twin state.

`53/108` nie jest jedną oceną poprawności systemu live, bo miesza fixturę
syntetyczną (np. chrome na zadanym monitorze, jeden monitor, zapamiętana
preferencja) z realnym planowaniem. `--portable` liczy warstwę, która ma sens
na aktualnym środowisku i odróżnia poprawne pytanie od luki autonomii. Różnica
między tymi liczbami nadal pokazuje realne braki planera bez LLM: parafrazy
„monitor z chrome" nie generują stabilnie `window/query/list ->
screen/query/capture(monitor_from)`, część wariantów „wszystkie monitory" nie
ustawia `scope=all`, a niektóre jawne numery monitorów kończą jako
`needs-selection` zamiast typed value/reject.

Stan `--real --llm` wymaga skonfigurowanego providera. Model można podać przez
`URIRUN_LLM_MODEL`/`LLM_MODEL` albo jawnie przez `--model`; dashboard dodatkowo
eksponuje niesekretny `/api/chat/config`, a frontend pobiera go przed requestem.
Sekrety providera (np. API key) nadal muszą być w środowisku procesu. Brak modelu
jest raportowany jako `planner-error` skip — to precondition providera, nie
zielony ani czerwony wynik architektury.

Po restarcie dashboardu i jawnie podanym modelu `openrouter/google/gemini-3.5-flash`
mały live smoke anchorów dał `1/3 checked`: jedna fraza rozwiązała się do
`monitor=2 · output=DP-2 · scope=monitor · 2160x3840`, dwie nadal wróciły jako
`needs-selection-unjustified`. To znaczy: tor LLM umie już wygenerować właściwy
data-flow, ale coverage jest rozkładem do mierzenia, nie stałą gwarancją jednej
próby.

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
