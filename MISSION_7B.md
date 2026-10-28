# Mission 7B — Préparer le premier benchmark Jev + CFR

Branche `claude/quirky-bardeen-1ddjmk`, repartie de `main` après la fusion de la PR #6.
Référence inchangée : **CFR V2 adaptative**.

**Aucun appel payant n'a été fait.** Toutes les mesures ci-dessous viennent de simulations
locales (CPU) ou de faux serveurs HTTP dans les tests. Chaque commande qui coûte de l'argent
refuse de s'exécuter sans `--approve-paid-calls` et un plafond en USD.

## 1. Résumé

| # | Demande | État |
| :-- | :-- | :-- |
| 1 | Intégration Jev officielle, `jev-1.14.0`, `/v1/systemone` | Vérifiée contre le SDK officiel. Deux défauts corrigés, dont un risque de fuite de clé — §2 |
| 2 | Tarif Jev 0,042 USD/M en entrée, sortie gratuite, conversion de devises | Fait. Les autres fournisseurs gardent leurs tarifs en CNY — §3 |
| 3 | Authentification, tokens, plafonds, erreurs, clé jamais exposée | Vérifié et testé (7 tests dédiés) — §4 |
| 4 | Pilote de 500 décisions Jev vs CFR + rapport de désaccords | Plan figé et versionné, coût ≤ 0,09 USD ; **exécution en attente de ton accord** — §5 |
| 5 | Benchmark `gate(0.5)` vs CFR seule, local, graines indépendantes | Protocole préenregistré, banc d'essai validé sur 72 000 mains locales, chiffrage de la course Jev — §6 |
| 6 | Demande d'autorisation Slumbot | Brouillon prêt, non envoyé — §7 |
| 7 | Aucun appel payant sans accord | Respecté |
| 8 | Tests et politiques | 748 tests verts (731 + 17) ; politiques intactes — §9 |

**Objectif : savoir si Jev améliore CFR, pas seulement l'intégrer.** La preuve viendra du
benchmark apparié du §6, qui est le seul à mesurer un effet en jetons. La simulation locale
montre déjà ce qu'il faudra pour conclure :
- Jev ne serait consulté que sur ~23 % des décisions ;
- détecter un effet de ±20 bb/100 contre les quatre profils demande ~150 000 mains et ~135 000 appels Jev ;
- c'est peu cher (≤ 24 USD), mais **la latence de Jev, encore inconnue, décidera de la durée**.

## 2. Intégration à l'API officielle TypeSafe

### 2.1 Contrat vérifié

Source : le SDK officiel `typesafe-sdk` 0.7.0, déjà installé. Son schéma est généré depuis
`https://api.typesafe.ai/openapi.json`.

| Point | Officiel | Chez nous (`provider.py`) |
| :-- | :-- | :-- |
| Endpoint | `POST https://api.typesafe.ai/v1/systemone` | identique |
| Authentification | `Authorization: Bearer <clé>` | identique, seul en-tête envoyé |
| Requête | `{state, model, questions}` ; question `choice` avec `criteria` | identique : la requête d'une salle |
| Réponse | `{model, answers, usage{input_tokens, output_tokens}}` | lue telle quelle |
| Réponse `choice` | `choice`, `confidence`, `probabilities` | validés (somme, cohérence, bornes) |
| Coût | « Output tokens are currently free of charge » | tarif de sortie à 0 |
| Diagnostic | en-tête `x-typesafe-request-id` | **ajouté** au journal de l'appel |
| Limitation de débit | `retry-after` / `retry-after-ms` | **désormais respecté**, plafonné à 30 s |

### 2.2 Défauts corrigés

1. **Risque de fuite de clé.**
   - Une entrée `provider: "jev"` sans `key_env` ni `base_url` explicites héritait des valeurs
     DeepSeek par défaut : elle envoyait la **clé DeepSeek** à `api.typesafe.ai`, avec le modèle
     `deepseek-flash`.
   - Un test existant (`test_jev_keeps_native_protocol`) le faisait d'ailleurs sans le vérifier.
   - Désormais, une entrée Jev reçoit les valeurs officielles pour tout champ non fourni :
     `https://api.typesafe.ai`, `JEV_API_KEY`, `jev-1.14.0`, tarifs USD. Un champ fourni
     explicitement n'est jamais écrasé.
2. **Modèle versionné.**
   - Le registre d'exemple (`examples/entries.example.json`) épingle `jev-1.14.0` dans `model` et
     `expected_model`.
   - Le pilote et le benchmark épinglent aussi `jev-1.14.0` : une réponse servie par un autre
     modèle est rejetée et arrête la course après un seul appel (< 0,0002 USD).

### 2.3 Non vérifié (sans clé ni accord)

- Aucun appel réel, y compris `GET /v1/models`.
- Le nom exact renvoyé par l'API pour `jev-1.14.0` reste à confirmer. Le premier appel du pilote
  le vérifie.

## 3. Tarifs et devises

- **Jev** : 0,042 USD par million de tokens d'entrée, sortie gratuite.
  - Le SDK officiel confirme que la sortie est gratuite. OpenRouter et Vercel AI Gateway affichent
    0,042 USD/M pour Jev 1.14 ; Requesty et Maxim affichent 0,04 USD.
  - Le prix exact peut dépendre de la route : 0,042 est la valeur la plus haute, donc la plus prudente.
- **Champs ajoutés à `Entry`** : `input_usd_per_million` et `output_usd_per_million`. Les tarifs
  CNY existants ne bougent pas. `Entry.prices_cny(rate)` convertit au taux configuré.
- **Taux de change** : `POKERBENCH_USD_CNY_RATE`, **6,71 par défaut**.
  - Source : cours moyen du 09/09/2026, 6,708 selon currencybeacon.com, arrondi vers le haut.
  - Aucun cours d'octobre n'a été trouvé. Mets la valeur du jour dans `.env` pour plus de précision.
  - La valeur 0 bloque tout appel facturé en USD avant le réseau.
- **Budgets** : ils restent comptés en CNY, comme toute l'application. Chaque appel Jev garde
  aussi `charge_usd` et le taux utilisé.
- **Autres fournisseurs** : DeepSeek et les autres gardent leurs tarifs CNY ; c'est testé.

L'ordre de grandeur rend le taux presque sans effet. Une décision consomme ~940 tokens d'entrée,
soit ≈ 0,00004 USD ≈ 0,0003 CNY.

## 4. Authentification, tokens, plafonds, erreurs

| Comportement | Test (`test_mission7b.py`) |
| :-- | :-- |
| En-tête `Authorization: Bearer <JEV_API_KEY>` et rien d'autre ; modèle `jev-1.14.0` | `test_jev_call_authenticates_counts_tokens…` |
| Coût = tokens d'entrée × 0,042 / 10⁶ × taux ; sortie gratuite ; `charge_usd` et `request_id` journalisés | idem |
| La clé n'apparaît dans aucun fichier écrit (base d'appels, décisions, réponses) | idem, et dans les tests du pilote |
| Mauvais modèle → rejet avant toute action, décision non enregistrée | `test_wrong_model_is_rejected…` |
| 401 → pas de nouvelle tentative, message sans la clé, même si le serveur la renvoie | `test_auth_failure_is_not_retried…` |
| 429/503 → nouvelle tentative après le délai demandé (plafonné à 30 s), au plus 3 essais | `test_rate_limit_waits_as_asked…` |
| Budget insuffisant ou taux à 0 → refus **avant** le réseau | `test_budget_and_missing_rate_stop…` |

Ce qui existait déjà et reste en place :
- réservation de budget avant chaque appel (plafonds global et par course) ;
- mise en cache de chaque décision par identifiant : une requête n'est jamais payée deux fois ;
- caviardage des clés personnelles.

## 5. Pilote de 500 décisions (`backend/pokerbench/jev_pilot.py`)

### 5.1 Plan figé avant tout appel

**Contenu du plan**
- 500 points de décision de CFR V2 adaptative, tirés de mains locales synthétiques (graine 74001,
  200 mains contre chacun des profils hyper, TAG, station et equity).
- Stratification : 150 preflop, 150 flop, 100 turn, 100 river.
- Fichier : `artifacts/mission7b/pilot-plan.jsonl.gz`, reproductible au bit près (testé).
  - SHA-256 du contenu : `1502acf0ef01dc82…`
  - SHA-256 du fichier : `25d7d9b1fe203f2f…`
- Chaque requête est exactement celle qu'une salle envoie à un modèle. Aucune carte cachée,
  aucun historique personnel.

**Mesures prévues**
- réponses valides, latence (médiane et p90), tokens facturés, coût réel ;
- accord avec CFR : action principale, type d'action (fold/passif/agressif), variation totale ;
- ventilation par rue, par adversaire et selon qu'on fait face à une mise ;
- matrice CFR → Jev, masse que Jev met sur l'action préférée de CFR, 15 plus grands désaccords
  avec la situation complète.

**Coût** (`python -m pokerbench.jev_pilot estimate`) :
- requêtes de 3 768 octets en moyenne ;
- borne haute **0,090 USD** (≈ 0,60 CNY), c'est-à-dire la réserve du Provider ;
- coût attendu ≈ **0,020 USD**.

### 5.2 Exécution, sur ton accord explicite

```bash
cd backend
export JEV_API_KEY=…                       # dans .env, jamais commité
python -m pokerbench.jev_pilot run --output ../data/pilot7b --max-usd 0.25 --approve-paid-calls
python -m pokerbench.jev_pilot analyze ../data/pilot7b/answers.jsonl --output ../reports/jev-pilot
```

**Pendant la course**
- au plus 4 requêtes simultanées ;
- arrêt immédiat si le modèle n'est pas `jev-1.14.0` ou si le budget est atteint ;
- une reprise réutilise les réponses déjà enregistrées, sans nouvel appel.

**Résultat** : le rapport `reports/jev-pilot/pilot-report.md` est généré automatiquement. Le
circuit complet est testé contre un faux serveur Jev.

Le pilote ne dit rien sur la force de jeu : un désaccord ne dit pas qui a raison.

## 6. Benchmark hybride `gate(0.5)` vs CFR seule (`backend/pokerbench/mission7.py`)

### 6.1 Protocole préregistré

- **Bras.** Référence : CFR V2 adaptative (V2 300k). Hybride : la même politique, qui consulte
  le conseiller quand CFR sort de son arbre ou quand son action principale pèse moins de 50 %.
- **Adversaires et graines.** Hyper, TAG, station et equity. Graines jamais utilisées :
  donnes 175001-175003, politiques 185001-185003.
- **Conditions de jeu.** Bouton alterné, 200 BB remis à zéro à chaque main, statistiques
  publiques exposées.
- **Comparaison appariée.** Les deux bras jouent les mêmes donnes avec les mêmes graines.
- **Alignement aléatoire** (`hybrid.py` modifié). L'hybride tire avec le générateur de CFR.
  Sans consultation, ou si le conseiller échoue, il joue **exactement** la main de CFR ; c'est
  testé sur des mains complètes. Le seul écart entre les bras est donc l'effet du conseiller.
- **Métrique.** bb/100 net à 5 % de rake (plafond 3 BB, pas de rake sans flop). Différence
  appariée par main, IC 95 % sur blocs de deux mains.
- **Décision.** L'hybride est accepté seulement si l'IC de la différence est entièrement
  au-dessus de zéro contre au moins un adversaire, et entièrement en dessous contre aucun.
  Au-delà de 1 % de consultations en échec, le bras est invalide.

### 6.2 Validation locale du banc d'essai

72 000 mains, sans aucun appel : 2 000 mains × 3 graines × 4 adversaires × 3 bras.
Données complètes : `artifacts/mission7b/local-benchmark.json`.

**Référence CFR V2 adaptative**, bb/100 sur 6 000 mains par adversaire :
- hyper +455 [255 ; 656]
- equity +186 [98 ; 273]
- station +96 [13 ; 179]
- TAG +23 [−16 ; 61]

**Bras témoin « null »** : le conseiller est CFR V2 adaptative elle-même, recalculée avec ses
propres tirages d'équité. Aucun effet n'est attendu, et aucun n'est trouvé : **4 verdicts
« inconclusive »**.

| Adversaire | Différence appariée (bb/100) | Mains identiques | Taux de consultation | σ apparié (bb/main) | Mains pour ±20 |
| :-- | --: | --: | --: | --: | --: |
| hyper | +28 [−49 ; +106] | 89,6 % | 20,9 % | 31,0 | 92 011 |
| equity | −9 [−46 ; +28] | 86,9 % | 24,7 % | 14,7 | 20 618 |
| station | −11 [−62 ; +40] | 79,7 % | 25,1 % | 20,1 | 38 884 |
| TAG | −1 [−15 ; +13] | 96,6 % | 22,2 % | 5,5 | 2 936 |

**Bras de substitution « CFR V3 »** : une politique réellement différente. Le banc d'essai
**détecte** les écarts :
- hyper : −198 [−316 ; −79], verdict « worse » ;
- station : +91 [22 ; 160], verdict « better » ;
- equity et TAG : non concluant.

Selon la règle, ce bras serait **refusé** (pire contre hyper). Ce résultat rejoint celui de la
mission 6 et montre que la règle bloque un gain partiel payé par une perte ailleurs.

### 6.3 Chiffrage de la course Jev

Jev est consulté sur ~0,26 (TAG) à ~0,94 (station) décision par main. Le tableau utilise les
σ du bras témoin ; si Jev s'écarte de CFR autant que V3, compter environ le double.

| Précision visée | Mains au total (4 adversaires) | Appels Jev | Coût attendu | Borne haute |
| :-- | --: | --: | --: | --: |
| ±50 bb/100 (étape 1) | ≈ 24 700 | ≈ 21 600 | ≈ 0,9 USD | 3,9 USD |
| ±20 bb/100 (étape 2) | ≈ 154 400 | ≈ 135 000 | ≈ 5,3 USD | 24,3 USD |
| ±20, avec la variance de V3 | ≈ 326 700 | ≈ 258 000 | ≈ 10,2 USD | 46,4 USD |

**La contrainte réelle est le temps.** Avec une latence d'1 s par appel en séquentiel, 135 000
appels prennent ~37 h. Le pilote mesurera cette latence.

**Proposition, sur ton accord.**
1. Le pilote (≤ 0,09 USD).
2. L'étape 1, contre TAG et equity d'abord, les deux profils les moins bruités. La commande
   ci-dessous joue 6 000 mains par adversaire et par bras, soit ~6 600 appels Jev : ≈ 0,26 USD
   attendus, borne haute 1,2 USD. Précision atteinte : ±14 bb/100 contre TAG, ±37 contre equity.
3. L'étape 2 seulement si l'étape 1 montre un signal.

Commande (refusée sans accord) :

```bash
python -m pokerbench.mission7 jev --hands 2000 --opponents tag,equity --output ../data/m7b-jev --max-usd 5 --approve-paid-calls
```

Commande locale gratuite qui reproduit le §6.2 :

```bash
python -m pokerbench.mission7 local --hands 2000 --workers 4 --output /tmp/m7b
```

## 7. Slumbot

Le brouillon de demande d'autorisation est dans `reports/slumbot-authorization-request.md`.
- Message en anglais pour Eric Jackson.
- Volume proposé : 2 agents × ~42 000 mains, une requête à la fois, ≥ 0,5 s d'intervalle,
  recul sur erreur, arrêt sur demande.
- Résultats publiés en agrégé seulement, avec citation de Slumbot.

**Rien n'a été envoyé et aucune main n'a été jouée.** À compléter : nom, e-mail, période.

## 8. Ce dont j'ai besoin de ta part

1. **Accord pour le pilote** : ≤ 0,25 USD de plafond, borne attendue 0,09 USD, ainsi que
   `JEV_API_KEY` dans ton `.env`. Je lance `run` puis `analyze` et je livre le rapport de désaccords.
2. Selon le pilote, **accord pour l'étape 1** du benchmark (≤ 5 USD).
3. Pour Slumbot : relire et envoyer la demande toi-même, ou me dire par quel canal.
4. Optionnel : le taux USD/CNY du jour, si tu veux remplacer 6,71.

## 9. Fichiers et tests

**Nouveaux fichiers**
- `backend/pokerbench/jev_pilot.py`
- `backend/pokerbench/mission7.py`
- `backend/tests/test_mission7b.py` (17 tests)
- `artifacts/mission7b/pilot-plan.jsonl.gz`
- `artifacts/mission7b/local-benchmark.json`
- `reports/slumbot-authorization-request.md`

**Fichiers existants modifiés**
- `config.py` : tarifs USD, `prices_cny`, valeurs Jev par défaut, `POKERBENCH_USD_CNY_RATE`.
- `provider.py` et `official_adapter.py` : prix via `prices_cny` ; `retry-after` ; identifiant
  de requête.
- `compare.py` : fonctions de distribution découpées, `RecordedAdvisor.from_answers`.
- `hybrid.py` : tirage aligné sur CFR. C'est un changement de comportement par rapport à 7A,
  voulu pour l'appariement.
- `examples/entries.example.json` (Jev 1.14.0 épinglé) et `.env.example` (taux, commenté).
- `tests/test_retries.py` : **un seul test modifié**. `test_jev_keeps_native_protocol` fournit
  désormais une clé Jev et vérifie l'en-tête, car il envoyait auparavant la clé DeepSeek à
  TypeSafe. Aucun autre test n'a été touché.

**Résultats**
- Suite backend : **748 passed** (731 + 17 nouveaux).
- Politiques `.json.gz` intactes.

## 10. Limites

- L'API Jev n'a jamais été appelée : nom du modèle servi, latence, taux de réponses valides et
  vrai nombre de tokens restent à mesurer (pilote).
- Le tarif repose sur des pages de distributeurs : 0,042 USD (OpenRouter, Vercel) ou 0,04 USD
  (Requesty, Maxim). La gratuité de la sortie est confirmée par le schéma officiel.
- Le taux de change par défaut date du 09/09/2026.
- Les σ du §6.3 viennent de conseillers de substitution. Le σ réel de Jev ne sera connu qu'après
  l'étape 1.
- Une amélioration contre nos profils locaux ne vaudrait pas contre Slumbot : c'est l'objet de
  la phase Slumbot, soumise à autorisation.

Sources : SDK `typesafe-sdk` 0.7.0 (schéma `api.typesafe.ai/openapi.json`) ·
[OpenRouter — Jev 1.14](https://openrouter.ai/typesafe/jev-1.14) ·
[Requesty — jev 1.14.0](https://www.requesty.ai/models/typesafe/jev-1.14.0) ·
[Maxim — jev 1.14.0](https://www.getmaxim.ai/bifrost/model-library/compare/typesafe/jev-1.14.0.md) ·
[Cloudprice](https://cloudprice.net/models/typesafe-ai-jev-1-14) ·
[currencybeacon USD/CNY](https://currencybeacon.com/index.php/rates/USD/CNY).
