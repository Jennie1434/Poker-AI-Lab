# Sauvegarde Missions 1–3 — état au moment de la reprise

> **Mise à jour : la Mission 3 est terminée.** Ce fichier décrit l'état laissé par Codex. L'analyse finale, les fréquences et la synthèse sont dans `MISSION_3.md` et `artifacts/mission3/analysis.*`, `frequencies.json`. Les 11 expériences rejouées sont identiques octet par octet à celles listées ici.

Sauvegarde demandée le 2026-10-25 à 22:32:54 CET.
Base : `549983a59104eee12cf7055cbc0b1793b0adb773`. Branche demandée : `codex/missions-1-3`.
Message de commit : `Sauvegarde Missions 1-3 (Mission 3 en cours)`.

## Arrêt du développement et inventaire

Aucun nouveau développement ni correction dans cette sauvegarde. Seul ce fichier d’état a été créé après la demande. Les calculs déjà lancés avaient terminé : aucun processus de benchmark/audit mission 3 n’était encore actif lors de l’inventaire. Aucun calcul supplémentaire n’a été lancé.

`git status --short`, `git diff --stat` et `git diff --stat 549983a` ont été exécutés. Les diffs des fichiers suivis étaient vides : tous les ajouts de code/documentation étaient non suivis et les artefacts ignorés. L’inventaire ci-dessous comprend ces ajouts ainsi que les résultats ignorés ; les dépendances installées, caches et configuration privée sont exclus.

## Terminé

- Missions 1 et 2 : audit, interface d’agent, politiques Random/Heuristic/Equity, smoke local, benchmark, tableau de bord, tests et résultats conservés.
- Mission 3 : TightAggressiveAgent, plan multi-graines, orchestrateur de calcul, audit/rejeu, contrôles Treys/PokerKit et outils de diagnostics implémentés.
- Les 9 expériences principales sont terminées : **90 000 mains** (3 graines × 3 confrontations × 10 000). Chaque expérience alterne exactement 5 000 BTN/SB et 5 000 BB par siège.
- Les diagnostics 256 et 1024 simulations ont terminé **1 000 mains chacun**. La référence à 64 est constituée des 1 000 premières mains de la confrontation principale Equity/TAG à la graine 31001 ; elle n’a pas de dossier séparé.
- Audit des 20 000 mains de mission 2 et 101 378 décisions : aucune divergence de profit, d’observation ou de carte cachée détectée. Reproduction des politiques sur les 20 plus gros pots gagnés et 20 perdus de chaque expérience ; 80 showdowns vérifiés indépendamment avec Treys.
- Audit supplémentaire de 10 000 mains Equity/TAG (31001), 50 709 décisions et 40 gros pots : aucune divergence détectée ; vérification indépendante des 40 showdowns.
- Diagnostic CPU sur 200 états fixes : moyennes 4,99 / 8,76 / 24,48 ms pour 64 / 256 / 1024 simulations ; 19 et 20 décisions changées sur 200 par rapport à 64.
- Diagnostic river sans sélection selon le résultat : 200 mains sur 1 256 éligibles, équité uniforme moyenne 54,73 %, part de showdown contre la main réelle 16,00 %, écart 38,73 points (IC descriptif 95 % : 34,73 à 42,73). Les cartes réelles n’ont été utilisées que dans l’auditeur hors ligne.

## En cours ou restant à faire

- `MISSION_3.md` est un rapport de travail : protocole, audit et tables de gros pots rédigés, mais synthèse finale multi-graines non achevée.
- L’agrégation finale des résultats, les comparaisons appariées 64/256/1024 et le recalcul final du rake à 0/2/5/7 % n’ont pas été lancés. Les modules correspondants existent, mais aucun `artifacts/mission3/analysis.json` ou `analysis.csv` n’a encore été produit.
- Les fréquences finales des politiques et le tableau de bord mission 3 n’ont pas été générés. Le tableau de bord mission 2 est conservé.
- Aucun entraînement CFR/self-play, aucune connexion Jev et aucune intégration de site tiers n’ont été commencés.

## Résultats déjà enregistrés par graine

Lecture des manifests existants uniquement ; aucune nouvelle agrégation statistique. Rake 5 %, plafond 3 BB, no-flop-no-drop. Valeurs nettes en bb/100.

| Expérience | Statut | Mains | Agent A : bb/100 [IC 95 %] | Agent B : bb/100 [IC 95 %] |
| --- | --- | ---: | --- | --- |
| equity-v-heuristic-31001-s64 | complete | 10000 | equity : +43.0910 [38.9323 ; 47.2497] | heuristic : -63.0230 [-67.3245 ; -58.7215] |
| equity-v-heuristic-31002-s64 | complete | 10000 | equity : +46.1410 [42.0433 ; 50.2387] | heuristic : -65.8950 [-70.1362 ; -61.6538] |
| equity-v-heuristic-31003-s64 | complete | 10000 | equity : +43.7380 [39.5906 ; 47.8854] | heuristic : -63.7660 [-68.0491 ; -59.4829] |
| equity-v-tag-31001-s1024-diagnostic | complete | 1000 | equity : -190.1950 [-313.8266 ; -66.5634] | tag : +157.0550 [34.9769 ; 279.1331] |
| equity-v-tag-31001-s256-diagnostic | complete | 1000 | equity : -192.2000 [-313.4875 ; -70.9125] | tag : +159.6500 [39.9339 ; 279.3661] |
| equity-v-tag-31001-s64 | complete | 10000 | equity : -184.3722 [-222.2964 ; -146.4480] | tag : +152.0272 [114.5746 ; 189.4798] |
| equity-v-tag-31002-s64 | complete | 10000 | equity : -180.9549 [-218.8095 ; -143.1003] | tag : +148.8784 [111.5038 ; 186.2530] |
| equity-v-tag-31003-s64 | complete | 10000 | equity : -198.1618 [-235.2340 ; -161.0896] | tag : +166.0143 [129.4766 ; 202.5520] |
| tag-v-heuristic-31001-s64 | complete | 10000 | tag : +1.8830 [0.3022 ; 3.4638] | heuristic : -5.7780 [-7.3372 ; -4.2188] |
| tag-v-heuristic-31002-s64 | complete | 10000 | tag : +2.0500 [0.5285 ; 3.5715] | heuristic : -5.9770 [-7.4784 ; -4.4756] |
| tag-v-heuristic-31003-s64 | complete | 10000 | tag : +4.0575 [2.5066 ; 5.6084] | heuristic : -7.9975 [-9.5292 ; -6.4658] |

**Graine 1 Equity/TAG : −184,3722 bb/100 nets pour Equity**. Les graines 2 et 3 sont elles aussi terminées, comme indiqué ci-dessus. Aucune confrontation prévue ne manque ; l’analyse finale reste à faire.

## Commandes lancées et vérifications

```bash
.venv/bin/python -m pokerbench.mission3 run --workers 3 --output artifacts/mission3
.venv/bin/python -m pokerbench.mission3 audit artifacts/mission2/random-v-equity --output artifacts/mission3-audit/random-v-equity.json
.venv/bin/python -m pokerbench.mission3 audit artifacts/mission2/random-v-heuristic --output artifacts/mission3-audit/random-v-heuristic.json
.venv/bin/python -m pokerbench.mission3 audit artifacts/mission3/equity-v-tag-31001-s64 --output artifacts/mission3-audit/equity-v-tag-31001.json
.venv/bin/python -m pokerbench.mission3 cost artifacts/mission2/random-v-equity --output artifacts/mission3-audit/cost.json
.venv/bin/python scripts/mission3_review.py showdowns artifacts/mission2/random-v-equity artifacts/mission3-audit/random-v-equity.json artifacts/mission3-audit/showdowns-equity.json
.venv/bin/python scripts/mission3_review.py showdowns artifacts/mission2/random-v-heuristic artifacts/mission3-audit/random-v-heuristic.json artifacts/mission3-audit/showdowns-simple.json
.venv/bin/python scripts/mission3_review.py showdowns artifacts/mission3/equity-v-tag-31001-s64 artifacts/mission3-audit/equity-v-tag-31001.json artifacts/mission3-audit/showdowns-tag.json
.venv/bin/python scripts/mission3_review.py postmortem artifacts/mission3/equity-v-tag-31001-s64 artifacts/mission3-audit/equity-v-tag-31001.json artifacts/mission3-audit/postmortem-tag.json
.venv/bin/python scripts/mission3_review.py ranges artifacts/mission3/equity-v-tag-31001-s64 artifacts/mission3-audit/river-range-check.json
.venv/bin/python -m pytest -q
```

**Tests relancés spécialement pour cette sauvegarde : `641 passed in 19.23s`, code de sortie 0. Aucune correction effectuée.** Résultats antérieurs : 52 tests ciblés, 26 tests frontend, compilation TypeScript/Vite et smoke navigateur de l’application réussis.

## Commandes exactes de reprise

Aucune confrontation n’est inachevée. Pour reprendre uniquement l’analyse (non exécutée dans cette sauvegarde) :

```bash
.venv/bin/python -m pokerbench.mission3 analyze artifacts/mission3 --output artifacts/mission3/analysis.json
.venv/bin/python scripts/mission3_review.py frequencies artifacts/mission3 artifacts/mission3/frequencies.json
```

**Attention : les gros journaux exclus du commit restent présents localement, mais manqueront dans un clone GitHub.** L’analyse vérifie aussi leurs checksums. Pour les reconstruire dans un clone, rejouer les expériences dans de nouveaux dossiers, sans écraser les résultats sauvegardés :

```bash
.venv/bin/python -m pokerbench.mission3 run --workers 3 --output artifacts/mission3-reprise
.venv/bin/python -m pokerbench.mission3 analyze artifacts/mission3-reprise --output artifacts/mission3-reprise/analysis.json
```

Pour relancer individuellement chaque confrontation principale avec ses paramètres exacts :

```bash
.venv/bin/python -m pokerbench.benchmark --hands 10000 --agent-a equity --agent-b tag --deck-seed 31001 --policy-seed 41001 --equity-samples 64 --tag-samples 64 --measure-time --rake-percent 5 --rake-cap-bb 3 --no-flop-no-drop --output artifacts/mission3-reprise-individuelle/equity-v-tag-31001-s64
.venv/bin/python -m pokerbench.benchmark --hands 10000 --agent-a equity --agent-b tag --deck-seed 31002 --policy-seed 41002 --equity-samples 64 --tag-samples 64 --measure-time --rake-percent 5 --rake-cap-bb 3 --no-flop-no-drop --output artifacts/mission3-reprise-individuelle/equity-v-tag-31002-s64
.venv/bin/python -m pokerbench.benchmark --hands 10000 --agent-a equity --agent-b tag --deck-seed 31003 --policy-seed 41003 --equity-samples 64 --tag-samples 64 --measure-time --rake-percent 5 --rake-cap-bb 3 --no-flop-no-drop --output artifacts/mission3-reprise-individuelle/equity-v-tag-31003-s64
.venv/bin/python -m pokerbench.benchmark --hands 10000 --agent-a equity --agent-b heuristic --deck-seed 31001 --policy-seed 41001 --equity-samples 64 --tag-samples 64 --measure-time --rake-percent 5 --rake-cap-bb 3 --no-flop-no-drop --output artifacts/mission3-reprise-individuelle/equity-v-heuristic-31001-s64
.venv/bin/python -m pokerbench.benchmark --hands 10000 --agent-a equity --agent-b heuristic --deck-seed 31002 --policy-seed 41002 --equity-samples 64 --tag-samples 64 --measure-time --rake-percent 5 --rake-cap-bb 3 --no-flop-no-drop --output artifacts/mission3-reprise-individuelle/equity-v-heuristic-31002-s64
.venv/bin/python -m pokerbench.benchmark --hands 10000 --agent-a equity --agent-b heuristic --deck-seed 31003 --policy-seed 41003 --equity-samples 64 --tag-samples 64 --measure-time --rake-percent 5 --rake-cap-bb 3 --no-flop-no-drop --output artifacts/mission3-reprise-individuelle/equity-v-heuristic-31003-s64
.venv/bin/python -m pokerbench.benchmark --hands 10000 --agent-a tag --agent-b heuristic --deck-seed 31001 --policy-seed 41001 --equity-samples 64 --tag-samples 64 --measure-time --rake-percent 5 --rake-cap-bb 3 --no-flop-no-drop --output artifacts/mission3-reprise-individuelle/tag-v-heuristic-31001-s64
.venv/bin/python -m pokerbench.benchmark --hands 10000 --agent-a tag --agent-b heuristic --deck-seed 31002 --policy-seed 41002 --equity-samples 64 --tag-samples 64 --measure-time --rake-percent 5 --rake-cap-bb 3 --no-flop-no-drop --output artifacts/mission3-reprise-individuelle/tag-v-heuristic-31002-s64
.venv/bin/python -m pokerbench.benchmark --hands 10000 --agent-a tag --agent-b heuristic --deck-seed 31003 --policy-seed 41003 --equity-samples 64 --tag-samples 64 --measure-time --rake-percent 5 --rake-cap-bb 3 --no-flop-no-drop --output artifacts/mission3-reprise-individuelle/tag-v-heuristic-31003-s64
```

Le plan complet `mission3 run` reproduit aussi les deux diagnostics de 1 000 mains. Les sources et versions sont consignées dans chaque manifeste. Les temps mesurés ne sont pas censés être identiques entre machines.

## Vérification de format sans correction

`git diff --cached --check` signale les fins de ligne CRLF des exports CSV comme des espaces en fin de ligne. Les CSV sont conservés octet pour octet, sans normalisation, pour préserver leur état et leurs checksums. Aucun code ou résultat n’a été corrigé.

## Secrets et limites de sauvegarde

Aucun `.env`, secret, clé API, `.venv/`, `node_modules/`, configuration privée ou base de données ajouté. `.env.example` appartient déjà au commit de base et n’est pas modifié. Contrôle par motifs de tokens, clés privées et URL avec identifiants : aucun motif détecté dans les fichiers texte sélectionnés. Les captures proviennent des tests navigateur à données simulées. Les traces conservées sont exclusivement celles des expériences synthétiques hors ligne.

Le seuil d’exclusion appliqué est conservateur : **50 000 000 octets**. Les fichiers ci-dessous restent sur disque, sans suppression, compression ou découpage pour contourner la limite. Les manifests conservent leurs checksums originaux ; une sauvegarde Git seule ne contient donc pas tous les journaux de rejeu.

| Fichier exclu | Octets |
| --- | ---: |
| `artifacts/mission2/random-v-equity/decisions.jsonl` | 148279009 |
| `artifacts/mission2/random-v-heuristic/decisions.jsonl` | 65413623 |
| `artifacts/mission2/repeat-random-v-heuristic/decisions.jsonl` | 65413623 |
| `artifacts/mission3/equity-v-heuristic-31001-s64/decisions.jsonl` | 182029179 |
| `artifacts/mission3/equity-v-heuristic-31002-s64/decisions.jsonl` | 181428890 |
| `artifacts/mission3/equity-v-heuristic-31003-s64/decisions.jsonl` | 182268353 |
| `artifacts/mission3/equity-v-tag-31001-s64/decisions.jsonl` | 108571756 |
| `artifacts/mission3/equity-v-tag-31002-s64/decisions.jsonl` | 108514537 |
| `artifacts/mission3/equity-v-tag-31003-s64/decisions.jsonl` | 107657932 |
| `artifacts/mission3/tag-v-heuristic-31001-s64/decisions.jsonl` | 72687965 |
| `artifacts/mission3/tag-v-heuristic-31002-s64/decisions.jsonl` | 72784938 |
| `artifacts/mission3/tag-v-heuristic-31003-s64/decisions.jsonl` | 73217225 |

## Liste exacte des fichiers de cette sauvegarde

**79 fichiers**, tous présents et sélectionnés pour le commit. Cette liste inclut ce fichier d’état. Les fichiers du commit de base restent inchangés.

```text
AUDIT_POKER_AI_LAB.md
BENCHMARK_LAB.md
MISSION_3.md
MISSION_3_ETAT.md
artifacts/mission2/dashboard.html
artifacts/mission2/random-v-equity/experiment.json
artifacts/mission2/random-v-equity/hands.csv
artifacts/mission2/random-v-heuristic/experiment.json
artifacts/mission2/random-v-heuristic/hands.csv
artifacts/mission2/repeat-random-v-heuristic/experiment.json
artifacts/mission2/repeat-random-v-heuristic/hands.csv
artifacts/mission3-audit/cost.json
artifacts/mission3-audit/equity-v-tag-31001.json
artifacts/mission3-audit/postmortem-tag.json
artifacts/mission3-audit/random-v-equity.json
artifacts/mission3-audit/random-v-heuristic.json
artifacts/mission3-audit/river-range-check.json
artifacts/mission3-audit/showdowns-equity.json
artifacts/mission3-audit/showdowns-simple.json
artifacts/mission3-audit/showdowns-tag.json
artifacts/mission3-pilot/decisions.jsonl
artifacts/mission3-pilot/experiment.json
artifacts/mission3-pilot/hands.csv
artifacts/mission3/equity-v-heuristic-31001-s64/experiment.json
artifacts/mission3/equity-v-heuristic-31001-s64/hands.csv
artifacts/mission3/equity-v-heuristic-31001-s64/runtime.json
artifacts/mission3/equity-v-heuristic-31002-s64/experiment.json
artifacts/mission3/equity-v-heuristic-31002-s64/hands.csv
artifacts/mission3/equity-v-heuristic-31002-s64/runtime.json
artifacts/mission3/equity-v-heuristic-31003-s64/experiment.json
artifacts/mission3/equity-v-heuristic-31003-s64/hands.csv
artifacts/mission3/equity-v-heuristic-31003-s64/runtime.json
artifacts/mission3/equity-v-tag-31001-s1024-diagnostic/decisions.jsonl
artifacts/mission3/equity-v-tag-31001-s1024-diagnostic/experiment.json
artifacts/mission3/equity-v-tag-31001-s1024-diagnostic/hands.csv
artifacts/mission3/equity-v-tag-31001-s1024-diagnostic/runtime.json
artifacts/mission3/equity-v-tag-31001-s256-diagnostic/decisions.jsonl
artifacts/mission3/equity-v-tag-31001-s256-diagnostic/experiment.json
artifacts/mission3/equity-v-tag-31001-s256-diagnostic/hands.csv
artifacts/mission3/equity-v-tag-31001-s256-diagnostic/runtime.json
artifacts/mission3/equity-v-tag-31001-s64/experiment.json
artifacts/mission3/equity-v-tag-31001-s64/hands.csv
artifacts/mission3/equity-v-tag-31001-s64/runtime.json
artifacts/mission3/equity-v-tag-31002-s64/experiment.json
artifacts/mission3/equity-v-tag-31002-s64/hands.csv
artifacts/mission3/equity-v-tag-31002-s64/runtime.json
artifacts/mission3/equity-v-tag-31003-s64/experiment.json
artifacts/mission3/equity-v-tag-31003-s64/hands.csv
artifacts/mission3/equity-v-tag-31003-s64/runtime.json
artifacts/mission3/plan.json
artifacts/mission3/tag-v-heuristic-31001-s64/experiment.json
artifacts/mission3/tag-v-heuristic-31001-s64/hands.csv
artifacts/mission3/tag-v-heuristic-31001-s64/runtime.json
artifacts/mission3/tag-v-heuristic-31002-s64/experiment.json
artifacts/mission3/tag-v-heuristic-31002-s64/hands.csv
artifacts/mission3/tag-v-heuristic-31002-s64/runtime.json
artifacts/mission3/tag-v-heuristic-31003-s64/experiment.json
artifacts/mission3/tag-v-heuristic-31003-s64/hands.csv
artifacts/mission3/tag-v-heuristic-31003-s64/runtime.json
backend/pokerbench/agents.py
backend/pokerbench/benchmark.py
backend/pokerbench/benchmark_dashboard.py
backend/pokerbench/local_play.py
backend/pokerbench/mission3.py
backend/tests/test_agents.py
backend/tests/test_benchmark.py
backend/tests/test_mission3.py
frontend/test-results/advisor-mobile.png
frontend/test-results/benchmark-dashboard-desktop.png
frontend/test-results/benchmark-dashboard-mobile.png
frontend/test-results/overview-mobile.png
frontend/test-results/personal-room.png
frontend/test-results/public-overview.png
frontend/test-results/public-replay-winners.png
frontend/test-results/replay-mobile.png
frontend/test-results/rooms-mobile.png
frontend/test-results/rooms-zh.png
frontend/tests/benchmark-dashboard.mjs
scripts/mission3_review.py
```

## Inventaire complet des ajouts avant sauvegarde

La liste exacte ci-dessus, hors `MISSION_3_ETAT.md` créé pour la sauvegarde, plus les 12 journaux exclus listés précédemment constitue l’inventaire des 90 fichiers de travail et résultats présents lors de l’inspection initiale. Les sorties reproductibles d’installation (dépendances, caches, bundle frontend) et la configuration locale privée ne font pas partie des livrables Git.
