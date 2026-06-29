# Generacje testów urirun — drabina obalania błędnej architektury wnioskowania

<!-- docs-nav -->
📖 **Dokumentacja urirun:** [Architektura](ARCHITECTURE.md) · [Autonomia](AUTONOMY_ARCHITECTURE.md) · [Retrieval](EXPERIENCE_RETRIEVAL.md) · **Generacje testów** · [Decision Loop](DECISION_LOOP.md)
<!-- /docs-nav -->

Status: 2026-06-29.

## Zasada projektowa

Generacja testów jest dobra wtedy, gdy jej **niezmiennik pada pod konkretną
błędną architekturą wnioskowania**. Nie „czy działa", tylko „jaką fałszywą
hipotezę o systemie obala". Dlatego każdą generację definiuję przez wadliwą
architekturę, którą złapie. Jeśli system jest zbudowany źle w sposób X, niezmiennik
generacji X **musi** zaświecić na czerwono.

Każda generacja = **ziarno** (jeden przykład) + **transformacje metamorficzne**
(rozgałęzienie z przewidywalnym wpływem na właściwości) + **niezmienniki**
(predykaty nad odpowiedzią, nie sztywne flow). Tryb: *offline* (oracle z
wstrzykniętą fixturą twina) bada logikę; *live* (HTTP, env czytany z odpowiedzi)
bada prawdziwy system. Zweryfikowane warianty zasilają indeks z
[EXPERIENCE_RETRIEVAL.md](EXPERIENCE_RETRIEVAL.md) jako known-good epizody.

Gen 1 (rozwiązanie env-enum dla zrzutu) i jej żywy harness są zrobione. Poniżej
Gen 2–Gen 11, rosnąco wg głębi wnioskowania. **Gen 2–11 są dostarczone jako
działające przykłady** (`gen2_data_flow.py`, `gen3_reversible.py`,
`gen4_state_router.py`, `gen5_cross_target.py`, `gen6_recall_adaptation.py`,
`gen7_effect_honesty.py`, `gen8_verification.py`, `gen9_preference_memory.py`,
`gen10_idempotence.py`, `gen11_capability_acquisition.py`) — każda z mutantem i
asercją, że niezmiennik go łapie.

## Drabina

| Gen | Obala błędną architekturę | Ziarno | Transformacja | Niezmiennik | Hak urirun |
|---|---|---|---|---|---|
| **2 · data-flow** ✅ | „kroki są niezależne; referencja do wyniku rozwiązuje się do wartości domyślnej, gdy źródła brak" | łańcuch `list → capture(monitor_from=…)` | usuń/wyzeruj referowane pole; przestaw kroki; dwa kroki produkują to samo pole; głęboka ścieżka | wartość referowana == wartość producenta; źródło `null` → typed block, nie śmieć; referencja wymaga `depends_on` i wcześniejszego kroku; brak cichego defaultu | `dispatch._flow_scheme_*`, `_resolve_artifact_value`, mechanizm `monitor_from` |
| **3 · odwracalność** ✅ | „`reversible` to etykieta, nie zdolność; system ufa fladze" | mutujący flow `close → write` | wstrzyknij awarię na kroku k; krok deklaruje `reversible:true` bez inverse (kłamstwo); operacja nieodwracalna bez confirm | każdy krok-komenda ma inverse albo jest zablokowany; awaria → ledger cofa świat do stanu początkowego (w odwrotnej kolejności); `reversible:false` → blok pre-exec, zero residuum | `reversible.ReversibleProcess`, `ledger_from_execution`, `rollback_partial_flow`, `Transition`, contract `inverse`/`reversible` |
| **4 · router = funkcja stanu** ✅ | „routing decydowany raz i cache'owany" | `capture --scope browser` przy CDP żywym vs martwym | CDP martwy → musi pojawić się `ensure`; po `ensure` sesja żyje → kolejny krok nie może użyć starej diagnozy; monitor odłączony w trakcie; node offline między planem a exec | ten sam intent + zmiana stanu → inny plan (`ensure`/inny `runsOn`); diagnoza sprzed `ensure` nie bramkuje kroku po `ensure`; blok, gdy naprawdę nieosiągalne | `preconditions.ensure`, `cdp.start_session/reachable`, router accept per-krok, `node_health` |
| **5 · cross-target** ✅ | „wszystko po cichu spada na host" | ta sama operacja, prompt nazywa host vs `node:lenovo` vs service | nazwij jawny node; nic (host default); node offline; service; miks targetów; dwuznaczny alias | `runsOnByStep` zgodny z nazwanym/wywnioskowanym targetem; nieosiągalny target → typed block, **nie** cichy fallback na host; efekt/safety zachowane przez transport; jawny wybór ma pierwszeństwo | `discovery.discover_mesh`, `_route_targets_active`, `_apply_host_default_*`, `node_dispatch.run_node_uri`, `routing.runsOnByStep` |
| **6 · adaptacja recall** ✅ | „recall odtwarza zapisany flow dosłownie" | epizod zapamiętany pod fingerprintem A | uruchom przy tym samym fp (reuse ok); przy innym fp/po zmianie env (musi re-resolve); po drifcie inwentarza; parafraza intencji | wartości środowiskowe (monitor, endpoint) w recall **re-rozwiązane** wobec bieżącego inwentarza, nie z pamięci; inny fingerprint → re-plan, nie ślepy reuse; recall i tak przez tę samą bramę akceptacji | `TwinMemory.recall_flow_by_intent/recall_episode`, `experience_retrieval`, `environment_fingerprint` |
| **7 · uczciwość efektu** ✅ | „niszczycielskość wnioskowana z sentymentu NL (`is_destructive`)" | operacja mutująca | sformułuj łagodnie („posprzątaj", „ogarnij", „napraw") vs wprost („usuń", „zamknij"); zakop w długim benignym promptcie; eufemizm | werdykt safety/efekt **identyczny** przy każdym sformułowaniu (z `contract.effect`, nie z heurystyki); operacja destrukcyjna nie przechodzi, bo NL brzmiało łagodnie; benigna nie jest blokowana, bo NL brzmiało groźnie | `task_planner.is_destructive` (zapach do obalenia), `contract.effect`, `_looks_destructive`, gate `checkEffect` |
| **8 · uczciwość weryfikacji** ✅ | „`ok:true` na kroku == zadanie zrobione" | dowolne zadanie z `verify(state)` | wstrzyknij awarię kroku; krok zwraca `ok:true` bez realnego efektu (phantom); cel weryfikacji nieobecny | `verify(state)` False ⟹ wynik **nie** „done"; awaria → recovery nextIntent albo rollback, nie cichy stop; phantom-success złapany przez weryfikację | `contracts.flow_execution_verification`, `decision_loop.general_path_next_intent`, `urifix_bridge.try_urifix_repair` |
| **9 · selekcja→pamięć→auto-run** ✅ | „preferencja globalna (nie per-fingerprint) ALBO pytana za każdym razem" | dwuznaczny zrzut | dwuznaczny → odpowiedź → powtórz przy tym fp (auto) → powtórz przy innym fp (znów pyta) → drift unieważnia | zapamiętana preferencja działa **tylko** przy zgodnym fingerprincie; auto-run po remember; ponowne pytanie po drifcie; brak przecieku | `remember_preference/recall_preference/_preference_key`, rodzina human-task w dashboard, `environment_fingerprint` |
| **10 · idempotencja** ✅ | „powtórzenie wykonuje na ślepo ponownie" | mutująca op + query op | uruchom dwa razy; przez przycisk repeat; współbieżnie | powtórzenie query → ten sam wynik, zero dodatkowej mutacji; powtórzenie mutacji → guard idempotencji/recall, nie podwójny efekt; `remember` odpala raz | `repeatChatMessage`, `twin://host/memory/command/remember`, idempotencja tras command |
| **11 · capability acquisition** ✅ | „samorozszerzenie omija bramę" | eksport SVG→PNG z brakującym konektorem `img` i aplikacją `inkscape` | luka odzyskiwalna → wygeneruj/zainstaluj konektor; app nieodzyskiwalna → typed need; kłamliwy kontrakt → gate block; resume/rerun | wygenerowany kontrakt przechodzi tę samą admisję co ręczny; brak zdolności daje typed need, nie sukces; recovery wznawia, nie restartuje mutacji | `preconditions.ensure`, `request_capability`, `connector_scaffold`, contract gate, `contract_reversible` |

## Najgłębsze cztery (dlaczego obalają architekturę)

**Gen 11 — samorozszerzenie pod bramą.** To jest test tezy „robot może
rozszerzyć przestrzeń akcji, ale nie może rozszerzyć sobie uprawnień poza
kontraktem". Wadliwa architektura trafia na brak konektora/aplikacji i albo
udaje sukces, albo instaluje wygenerowany konektor bez admisji, albo przy
recovery restartuje cały flow. Generacja wymusza: typed need przy luce
nieodzyskiwalnej, ta sama brama admisji dla wygenerowanego kontraktu, oraz resume
od miejsca blokady bez ponawiania mutacji. Jeśli pada — samorozszerzenie jest
obejściem kernela, nie autonomią.

**Gen 4 — router jako funkcja stanu.** To jest test tezy „router = czysta funkcja
`plan(intent, twin_state, action_space)`". Twój własny ślad dowodzi, że ta sama
komenda daje inny plan zależnie od tego, czy sesja CDP żyje. Wadliwa architektura
liczy routing raz na początku i cache'uje. Generacja wstrzykuje **zmianę stanu w
trakcie** (ensure ożywia sesję) i sprawdza, że krok po `ensure` nie używa diagnozy
sprzed `ensure`. Jeśli pada — router nie jest funkcją stanu, tylko zamrożoną
decyzją.

**Gen 6 — adaptacja recall.** To jest test tezy „retrieval miękki, admisja twarda"
i „recall to materiał wyjściowy, nie cache omijający rozumowanie". Wadliwa
architektura odtwarza zapamiętany flow z **zaszytymi** wartościami (monitor 3,
endpoint 9222) niezależnie od bieżącego env. Generacja zmienia env po remember i
sprawdza, że recall **re-rozwiązuje** wartości wobec inwentarza. Jeśli pada — recall
to sztywne nagranie, a nie adaptacja, i system będzie po cichu robił złą rzecz w
zmienionym środowisku.

**Gen 7 — uczciwość efektu.** To jest test reguły reklasyfikacji: „gdzie heurystyka
zgaduje to, co kontrakt deklaruje — kasuj". Wadliwa architektura wnioskuje
niszczycielskość z NL (`is_destructive`), więc operacja destrukcyjna sformułowana
łagodnie przechodzi, a benigna brzmiąca groźnie jest blokowana. Generacja podaje tę
samą operację w wielu sformułowaniach i żąda **identycznego** werdyktu bramy. Jeśli
werdykt zależy od słów — safety stoi na sentymencie, nie na deklaracji, i to jest
dokładnie błędna architektura wnioskowania, którą trzeba usunąć (znana luka:
`is_destructive` wciąż żyje w torze no-LLM/ticket).

## Jak budować każdą generację

Klonuj szkielet z `nlmatrix/`:

1. **oracle/symulator domeny** — referencja poprawnego zachowania (np.
   `gen3_reversible.py` dla mutacji). Definiuje, względem czego mierzysz system.
2. **transformacje** — metamorficzne, każda z przewidywalnym wpływem na `expect`.
3. **properties** — niezmienniki; muszą mieć zęby (test karmi je **mutantem**
   reprezentującym błędną architekturę i sprawdza, że łapią).
4. **run / live_run** — offline na fixturze, potem ten sam checker na żywym HTTP.

Każda generacja, której nie da się zepsuć mutantem, jest bezwartościowa — dlatego
testy zawsze zawierają wariant „błędna architektura" i asercję, że niezmiennik
go wykrywa.

## Dostarczone

- Gen 1: `transforms.py` / `properties.py` / `twin_registry_sim.py` (offline) +
  `live_*` (HTTP). 108 wariantów offline, 54 frazy live.
- **Gen 3: `gen3_reversible.py` + `test_gen3.py`** — mutacja + ledger + rollback;
  oracle przechodzi, mutant (silnik ufający fladze `reversible`) jest łapany.
- **Gen 4: `gen4_state_router.py` + `test_gen4.py`** — routing przeliczany z
  bieżącego stanu; 8/8 oracle, mutant „initial snapshot cache" łapany tym samym
  checkerem (`stale-cdp-diagnosis`, `stale-cdp-capture`,
  `stale-monitor-domain`, `stale-node-reachability`). Generacja koduje tezę:
  `ensure`, drift monitora i offline node muszą wpływać na następny krok, nie
  tylko na pierwszy routing preview.
- **Gen 5: `gen5_cross_target.py` + `test_gen5.py`** — routing host vs `node:` vs
  service; 9/9 oracle, mutant „wszystko → host" łapany tym samym checkerem
  (`silent-host-fallback`, `unreachable-not-blocked`). Mutant = regresja naprawiona
  w tej sesji (usunięty guard `_has_explicit_remote_selection` wokół
  `_apply_host_default_*`), więc generacja jest bramą anty-regresyjną dla
  ekstrakcji target-resolution do `urirun-connector-router`.
  **Live: `gen5_live.py` + `test_gen5_live.py`** (opt-in, skip gdy :8194 down) —
  czyta realny mesh, framuje intent po każdym targecie i stosuje TEN SAM
  `gen5_cross_target.check` na żywym HTTP (`execute=0`, read-only). 5/5 na żywo:
  nieosiągalne nody (`android-web1`, `crm-api`) blokują (nie cichy host),
  `node:lenovo`→lenovo, `host+node:lenovo`→lenovo. Pierwsza z Gen 2–11 z domkniętym
  trybem **offline→live** wg spec — potwierdza, że wdrożony system jest honorowy.
- **Gen 6: `gen6_recall_adaptation.py` + `test_gen6.py`** — recall jako
  propozycja adaptowana do bieżącego środowiska; 7/7 oracle, mutant „literalny
  replay" łapany tym samym checkerem (`literal-recall-across-fingerprint`,
  `stale-env-value`, `preference-fingerprint-leak`,
  `missing-current-state-reference`). Generacja wymusza, że konkretne wartości
  env-enum z epizodu (np. monitor) nie przechodzą przez zmianę fingerprintu bez
  re-resolve/result-ref albo typed block.
- **Gen 2: `gen2_data_flow.py` + `test_gen2.py`** — `<key>_from` resolver; 6/6
  oracle, mutant „cichy default przy braku źródła" łapany (`silent-default`);
  referencja wymaga `depends_on` + wcześniejszego producenta. Hak: dokładnie
  mechanizm `monitor_from` naprawiony w tej sesji.
- **Gen 7: `gen7_effect_honesty.py` + `test_gen7.py`** — efekt z `contract.effect`,
  nie z NL; 9/9 oracle + metamorficzna niezmienniczość werdyktu po sformułowaniu;
  mutant `is_destructive` łapany (`effect-from-sentiment`): eufemizm „posprzątaj"
  przepuszcza `delete`, „zniszcz" blokuje `list`.
- **Gen 8: `gen8_verification.py` + `test_gen8.py`** — `verify(state)` po
  wykonaniu; 5/5 oracle, mutant „`ok:true` == done" łapany (`phantom-success`,
  `silent-stop`): krok bez realnego efektu nie jest „done", awaria daje recovery.
- **Gen 9: `gen9_preference_memory.py` + `test_gen9.py`** — preferencja kluczowana
  fingerprintem; sekwencja ambiguous→answer→reuse→inny-fp→reuse; mutant „global
  store" łapany (`preference-leak`): wybór z jednego env nie auto-uruchamia się w
  innym.
- **Gen 10: `gen10_idempotence.py` + `test_gen10.py`** — guard idempotencji po
  kluczu; 4/4 oracle, mutant „repeat re-wykonuje na ślepo" łapany
  (`double-mutation`): liczba mutacji == liczba różnych kluczy, query bez efektu.
- **Gen 11: `gen11_capability_acquisition.py` + `test_gen11.py`** — autonomiczny
  robot rozszerza przestrzeń akcji w runtime. 6/6 oracle, trzy mutanty łapane
  tym samym checkerem: cichy skip luki (`verify-honesty`), acquisition bez bramy
  (`ungated-acquisition`), restart zamiast wznowienia (`restart-instead-of-resume`).
  To domyka tezę: acquisition miękki, admisja twarda.
- **`run_ladder.py`** — zbiorczy runner egzekwujący META-niezmiennik drabiny:
  każda generacja musi mieć (1) mutanta w module (`buggy_*`/`Buggy*`), (2)
  test-mutanta asercjonujący złapanie, (3) zielony oracle. Brak któregokolwiek =
  czerwone. `10/10` — drabina jest samo-pilnująca: generacja bez zębów nie wejdzie.
