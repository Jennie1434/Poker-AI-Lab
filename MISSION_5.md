# Mission 5 — jouer contre notre IA, puis abstraction CFR V2

Repris depuis `main` après la fusion de la PR #1. Rapports relus : `MISSION_4.md`,
`MISSION_3.md`, `BENCHMARK_LAB.md`, `AUDIT_POKER_AI_LAB.md`. PokerKit reste l'unique
autorité sur les cartes, les actions légales et les gains. Les politiques V1 de la
mission 4 ne sont pas modifiées. Leur comportement est vérifié identique : 53 405
décisions enregistrées en mission 4 ont été rejouées avec le nouveau code, avec les
mêmes actions et les mêmes taux de repli.

## Synthèse

| Demande | Résultat |
| --- | --- |
| Jouer contre l'IA dans le navigateur | **Fait.** Table privée humain contre CFR, choix de la politique (V1 200k, V1 20k, V2 300k), cartes cachées, actions légales PokerKit, historique des mains et statistiques. **En bonus, un mode spectateur** IA contre IA. Testé dans un vrai Chromium, sur ordinateur et sur mobile. |
| Abstraction V2 | **Faite.** Trois tailles de relance, groupes tenant compte des tirages, traduction des relances adverses à la taille la plus proche. Synchronisée jeton par jeton avec PokerKit. |
| Budget mesuré | V2 : 200 000 itérations en 85 min CPU (V1 : 41 min) ; 300 000 en 2 h 10. |
| V1 contre V2 face à TAG | **V2 fait significativement mieux que V1** : **+19,5 bb/100 [+2,3 ; +36,7]** sur le plan corrigé, et **+17,8 [+0,1 ; +35,6]** sur des graines neuves. Les 6 graines vont dans le même sens. |
| Battre TAG | **Toujours non démontré.** La meilleure politique (V2 300k) passe en positif, à +8,7 [−7,4 ; +24,8] puis +6,2 [−10,3 ; +22,6] à 5 % de rake, mais l'intervalle contient zéro. Verdict : **non concluant**. |

**Bug trouvé par l'évaluation préenregistrée et rapporté tel quel** : dans la politique V2
exportée, l'ordre des tailles de relance changeait, si bien que 37 % des décisions de V2 sortaient
de son arbre. La correction et sa réévaluation ont été déclarées et commitées avant d'être lancées.
Les résultats d'origine restent publiés ci-dessous.

Ces résultats sont des simulations entre bots ; ils ne mesurent pas l'exploitabilité dans le jeu
réel et ne promettent aucun gain contre des humains.

## Ordre de livraison

| Commit | Contenu |
| --- | --- |
| `e673c84` | **Table jouable** humain contre CFR dans les salles privées, historique, statistiques, test navigateur réel |
| `710fc89` | Abstraction **V2** et **protocole de comparaison V1/V2 figé** avant toute main d'évaluation |
| `b64cc0d` | **Mode spectateur** IA contre IA (demandé en cours de mission) |
| `8210ce0` | Politiques V2 entraînées, V2 jouable dans les salles et le spectateur |
| `21b1e29` | Correction du bug d'ordre des tailles de V2, avec **amendement déclaré avant réévaluation** |
| (dernier commit) | Résultats, analyses et rapport |

La table a été livrée et poussée avant tout entraînement lourd, comme demandé.

## 1. Jouer contre l'IA dans le navigateur

### Utilisation

1. Lancer l'application (`README.md`), ouvrir **Play with models** (自己组局) et créer un
   compte. Aucune clé API ni invitation n'est nécessaire pour l'IA locale.
2. Dans la liste des adversaires, choisir **une** politique CFR, par exemple
   **CFR V1 · 200k**. Elle est présélectionnée par défaut.
3. **Create table & take a seat**, puis **Start game**. À votre tour, les boutons ne
   proposent que les actions légales calculées par PokerKit. Les montants de relance
   indiquent votre mise totale sur la street.
4. Sous la table : le journal de la main, le classement, puis **Hand history and
   statistics**. On y trouve les statistiques par joueur (mains, gain net, bb/100,
   mains gagnées, VPIP, PFR, abattages) et les mains récentes, dépliables avec toutes
   leurs actions.

### Fonctionnement

- **Fournisseur local `local_cfr`** (`backend/pokerbench/local_agents.py`). Les décisions
  de la salle passent par le même `Provider` que les modèles distants, mais la politique
  gelée est évaluée dans le processus : pas de réseau, pas de clé, coût nul. L'agent reçoit
  la même observation filtrée qu'un modèle distant : ses propres cartes, le board public et
  l'historique public. PokerKit valide l'action retournée.
- **Reproductibilité** : chaque décision est tirée avec une graine dérivée de son identifiant
  (`run:main:action`) et mise en cache comme toute décision de modèle. Une reprise après
  redémarrage rejoue exactement la même partie.
- **Choix de la politique** : `CFR V1 · 200k` (politique finale de la mission 4) et
  `CFR V1 · 20k` (instantané précoce, plus faible), et `CFR V2 · 300k`. Chaque entrée porte
  l'empreinte de son fichier de politique.
- **Restrictions** : une salle CFR est forcément **heads-up et en cash**, car l'abstraction
  ne connaît que ce format. Pour rester proche de la profondeur d'entraînement (200 BB), les
  deux stacks sont ramenés à 200 BB dès qu'un joueur atteint 400 BB, au lieu de 2 000 BB dans
  les autres salles. Les politiques CFR n'apparaissent jamais dans le classement officiel du
  benchmark.
- **Jetons fictifs** : capital virtuel de 10 000 unités, recave à 200 BB, comme les autres
  salles.
- **Confidentialité** : les cartes adverses restent `??` pendant la main. L'historique est
  construit à partir de la vue filtrée du propriétaire : une carte adverse n'y figure que si
  elle a été montrée à l'abattage, et aucune décision interne de l'agent n'est exposée.
  L'historique n'est accessible qu'au propriétaire de la salle.

### Tests de la table

- `backend/tests/test_cfr_rooms.py` (7 tests, avec le vrai `Provider` et la vraie politique) :
  - enregistrement des politiques, et absence dans le roster du benchmark ;
  - refus des salles CFR multi-joueurs ou SNG ;
  - **partie complète via l'API** (4 mains, contre V1 puis contre V2), avec cartes adverses cachées à chaque étape ;
  - décisions locales à coût nul ;
  - rejeu identique ;
  - historique et statistiques cohérents (somme des gains nulle), sans carte non montrée ;
  - refus de l'historique sans authentification ;
  - décision déterministe par identifiant.
- `frontend/tests/cfr-room.mjs`, **test réel dans Chromium**, sans maquette :
  - inscription, présélection de la politique et note CFR ;
  - création de la table et **6 mains complètes jouées en cliquant (28 actions humaines)**,
    en alternant check, call et relances ;
  - cartes adverses cachées pendant chaque main ;
  - statistiques et historique dépliable ;
  - affichage mobile (390 px) sans défilement horizontal ;
  - aucune erreur JavaScript.

  ```bash
  cd frontend && npm run build
  # backend isolé, données jetables :
  POKERBENCH_DATA_DIR=/tmp/pb-test ../.venv/bin/uvicorn pokerbench.api:app --app-dir ../backend --port 8097
  PB_BASE_URL=http://127.0.0.1:8097 node tests/cfr-room.mjs /tmp/captures
  ```


### Mode spectateur (IA contre IA)

Ajouté à votre demande pendant la mission. Menu **Spectate** (观战), sur un compte connecté :

- choisir deux agents parmi CFR V1 200k, CFR V1 20k, CFR V2 300k, TightAggressive, Equity, Heuristic
  et Random (un agent peut aussi jouer contre lui-même), puis **Start watching** ;
- les mains défilent à la table, une action par seconde, avec distribution automatique. On peut mettre
  en pause, avancer vite ou passer à la main suivante ;
- le spectateur voit les deux mains, mais chaque agent ne reçoit toujours que sa propre observation,
  par le même pont `play_action` que le benchmark. Format : heads-up, 200 BB à chaque main, bouton
  alterné ;
- le gain net, le bb/100 et les mains gagnées ne comptent une main **qu'une fois sa lecture terminée**,
  pour ne pas dévoiler le résultat avant la fin ;
- les sessions sont privées (propriétaire seulement), gardées en mémoire, limitées à 5 par compte et à
  2 000 mains chacune. Elles n'entrent jamais dans le classement officiel.

Tests : `backend/tests/test_spectator.py` (3 tests : partie CFR contre TAG, alternance du bouton, somme
nulle, accès refusé sans compte, limites, requêtes concurrentes jouées une seule fois) et
`frontend/tests/spectate.mjs` (Chromium réel : les deux mains visibles, statistiques, mobile sans
défilement horizontal).

## 2. Abstraction CFR V2

`backend/pokerbench/holdem_v2.py`, jeu `holdem-hu-abstract-v2`. V1 est conservée telle quelle.

| Dimension | V1 | V2 |
| --- | --- | --- |
| Tailles de relance | pot `r`, all-in `a` | **première mise de la street : ½ pot `h`, pot `r`, 1,5× pot `o`** (postflop) ; face à une relance : pot `r` ; all-in `a` |
| Groupes préflop | 8 | 8 (même table) |
| Groupes flop/turn | 8 groupes d'équité | **6 groupes d'équité × tirage (couleur ou quinte ouverte) = 12** |
| Groupes river | 8 | 8 |
| Traduction des relances adverses | toute relance non all-in devient `r` | **taille abstraite la plus proche**, en fraction du pot (écart logarithmique) |
| Mémoire des actions | séquence complète de toutes les streets | séquence complète de la street courante, **nombre de relances** des streets passées, et liste des actions légales |
| Profondeur | 2 relances dimensionnées, 3 au total par street | identique |

Toutes les tailles V2 sont des tailles que PokerKit propose réellement dans ce format : ½ pot,
pot et 1,5× pot postflop ; 2× et 3× préflop. Un test fait jouer **250 mains** en parallèle
dans PokerKit et dans l'arbre V2, en privilégiant les relances dimensionnées. Il vérifie à
chaque décision que les jetons engagés sont identiques, que l'historique reconstruit par l'agent
à partir des vraies relances est exact, que les actions légales coïncident et que la clé est la
même que celle du jeu abstrait.

**Problème détecté et corrigé avant tout entraînement** : avec l'historique complet et trois
tailles libres, la première version de V2 visitait 229 630 ensembles d'information en 3 000
itérations (V1 : 6 979). Chaque ensemble aurait été à peine entraîné. Deux décisions ont ramené
V2 à environ 9 800 ensembles : limiter les tailles multiples à la première mise de la street, et
résumer les streets passées. Le garde-fou du solveur a aussi détecté que ce résumé fusionnait
des états aux actions légales différentes. La liste des actions légales a donc été ajoutée à la
clé.

Limites qui demeurent : mémoire imparfaite des cartes et des actions passées, groupes fondés sur
l'équité contre une main aléatoire (avec un indicateur de tirage), aucun calcul d'exploitabilité
dans le jeu réel. **V2 n'est pas une stratégie GTO du no-limit complet.**

## 3. Budget d'entraînement

Coût mesuré avant de fixer le budget : 19,3 ms par itération pour V2, sur un cœur.

| Entraînement | Itérations | CPU | Ensembles d'information | Regret positif moyen / itération |
| --- | ---: | ---: | ---: | ---: |
| V1, graine 71001 (mission 4) | 200 000 | 2 452 s (41 min) | 8 063 | 0,0017 |
| V2, graine 72001 | 100 000 | 2 409 s | 9 844 | 0,0040 |
| V2, graine 72001 | 200 000 | 5 090 s (85 min) | 9 846 | 0,0023 |
| V2, graine 72001 | 300 000 | 7 772 s (2 h 10) | 9 847 | 0,0016 |
| V2, graine 72002 | 200 000 | 5 256 s | 9 848 | 0,0023 |

À itérations égales, V2 coûte environ 2,1 fois plus de CPU que V1 dans ces conditions. Les deux
entraînements V2 tournaient en parallèle, en même temps que des tests ; la mesure isolée donnait
19,3 ms contre 17,4 ms par itération. La politique V2 pèse 111 Ko compressée (V1 : 85 Ko). En jeu,
le coût par décision est presque le même : 1,85 à 1,98 ms pour V2, 1,8 ms pour V1.

## 4. Comparaison V1 / V2 contre TAG

Protocole (`backend/pokerbench/mission5.py`, commité avant toute main d'évaluation) :

- **Politiques** : V1 (mission 4, 200 000 itérations) ; V2 graine 72001 à **200 000 itérations**
  (comparaison principale, même nombre d'itérations) et à 300 000 ; V2 graine 72002 à 200 000
  (variance entre entraînements).
- **Adversaire** : TightAggressiveAgent, le seul agent de référence que V1 n'a pas battu.
- **Données indépendantes** : graines (81001, 91001), (81002, 91002), (81003, 91003), jamais
  utilisées à l'entraînement ni dans les missions précédentes (vérifié par un test).
  10 000 mains par graine et par politique, bouton strictement alterné. **Toutes les politiques
  jouent les mêmes donnes avec les mêmes graines**, ce qui permet des différences appariées main
  par main. Au total : 120 000 mains.
- **Mesure** : bb/100 net à 5 % de rake (plafond 3 BB, no-flop-no-drop), avec aussi 0, 2 et 7 % ;
  IC à 95 % sur des blocs de deux mains.
- **Verdicts fixés d'avance** : « V2 améliore V1 » seulement si l'IC de la différence appariée
  (V2 200k − V1) est entièrement positif ; une politique « bat TAG » seulement si son IC global
  est entièrement positif et que les trois graines sont positives.

### Résultats préenregistrés (V2 avec le bug, publiés tels quels)

Rake 5 %, 30 000 mains par politique (graines 81001–81003) :

| Politique | bb/100 net [IC 95 %] | Graines | Sorties d'arbre | Verdict |
| --- | ---: | --- | ---: | --- |
| V1 200k | −16,08 [−33,92 ; +1,76] | −25,7 / +1,5 / −24,0 | 0,2 % | non concluant |
| V2 200k | −8,45 [−25,31 ; +8,41] | −16,9 / +13,9 / −22,3 | **37 %** | non concluant |
| V2 300k | +1,60 [−14,27 ; +17,48] | −16,3 / +24,0 / −2,9 | **37 %** | non concluant |
| V2 graine 2 | −12,43 [−29,93 ; +5,08] | −32,5 / −0,2 / −4,6 | **39 %** | non concluant |

Différence appariée V2 − V1 : +7,63 [−10,05 ; +25,31], non concluante.

**Diagnostic.** Le taux de sortie d'arbre de 37 % (contre 0,2 % pour V1) a été analysé décision par
décision. La politique exportée stocke la configuration avec des clés triées, donc les tailles en
ordre `h, o, r`. L'agent rechargé énumérait les actions légales dans cet ordre, alors que
l'entraînement avait utilisé `h, r, o`. La fin de clé ne correspondait jamais, et chaque première
mise postflop basculait sur la règle de repli. Le test de synchronisation construisait l'abstraction
en mémoire, sans export : il ne pouvait pas voir le problème. Correction : tailles ordonnées par
fraction du pot, ce qui est l'ordre d'entraînement, donc **les politiques entraînées restent
valides sans réentraînement**. Un nouveau test passe par l'export et le rechargement réels ; il
échoue sans la correction. Après correction : **0 %** de sortie d'arbre sur les 12 626 décisions
enregistrées.

**Amendement**, commité avant de relancer quoi que ce soit (`21b1e29`) : le même plan est rejoué avec
le code corrigé, puis confirmé sur des graines neuves (83001–83003 / 93001–93003) avec les mêmes règles
de verdict.

### Résultats corrigés

Rake 5 %, plafond 3 BB, no-flop-no-drop ; 30 000 mains par politique et par jeu de graines.

| Politique contre TAG | Plan corrigé (81001–81003) | Graines | Confirmation (83001–83003) | Graines |
| --- | ---: | --- | ---: | --- |
| V1 200k | −16,08 [−33,92 ; +1,76] | −25,7 / +1,5 / −24,0 | −18,40 [−36,95 ; +0,15] | −19,1 / −14,8 / −21,3 |
| **V2 200k** | +3,38 [−13,67 ; +20,43] | −6,6 / +18,7 / −1,9 | −0,56 [−17,86 ; +16,74] | −4,2 / +7,2 / −4,7 |
| **V2 300k** | **+8,66 [−7,43 ; +24,76]** | −8,6 / +27,3 / +7,3 | **+6,16 [−10,31 ; +22,62]** | +9,7 / +7,2 / +1,7 |
| V2 graine 2 | +7,69 [−9,44 ; +24,81] | −8,1 / +16,5 / +14,6 | −1,30 [−18,73 ; +16,14] | −0,9 / +17,2 / −20,1 |

Toutes les politiques restent **non concluantes** contre TAG : aucun IC n'est entièrement positif.
V1 rejoué sur le plan corrigé donne des `hands.csv` **identiques octet par octet** à ceux de la
première exécution, ce qui confirme que V1 n'a pas été touché.

**Différences appariées** (mêmes donnes, mêmes graines, main par main) :

| Comparaison | Plan corrigé | Confirmation | Verdict |
| --- | ---: | ---: | --- |
| **V2 200k − V1** (principale) | **+19,46 [+2,25 ; +36,68]** (graines +19,1 / +17,2 / +22,2) | **+17,84 [+0,13 ; +35,55]** (+14,9 / +22,1 / +16,5) | **V2 meilleure, deux fois** |
| V2 300k − V2 200k | +5,28 [−4,01 ; +14,56] | +6,72 [−2,45 ; +15,89] | non concluant |
| V2 graine 2 − V2 graine 1 | +4,31 [−10,51 ; +19,13] | −0,74 [−16,31 ; +14,84] | non concluant |

À itérations égales, l'abstraction V2 apporte un gain mesuré d'environ **+18 à +19 bb/100 contre TAG**,
reproduit sur des données indépendantes. Les deux entraînements V2 ne diffèrent pas de façon
significative : le gain vient bien de l'abstraction, pas de la chance d'une graine d'entraînement.
Passer de 200 000 à 300 000 itérations améliore probablement le jeu (+5 à +7), sans que ce soit
démontré.

### Sensibilité au rake (V2 300k contre TAG)

| Rake (plafond 3 BB) | Plan corrigé | Confirmation |
| --- | ---: | ---: |
| 0 % | +15,15 [−1,12 ; +31,43] | +12,78 [−3,87 ; +29,42] |
| 2 % | +11,70 | +9,22 |
| 5 % | +8,66 [−7,43 ; +24,76] | +6,16 [−10,31 ; +22,62] |
| 7 % | +7,05 [−9,03 ; +23,14] | +4,52 [−11,94 ; +20,98] |

Pour V1, l'IC à 7 % est entièrement négatif sur les graines de confirmation (−19,98 [−38,52 ; −1,44]) :
avec un rake élevé, V1 perd contre TAG. Le rake coûte à V2 300k environ 6,5 bb/100 entre 0 et 5 %.

### Lecture

- V2 gagne davantage de mains contre TAG que V1 (74 à 76 % contre 71 %). Hypothèse non mesurée ici :
  les mises au demi-pot et les surmises lui donnent des options de valeur et de pression que V1 n'avait
  pas. Une analyse par taille de pot le vérifierait.
- L'écart-type par main (≈ 14–16 BB) laisse un IC d'environ ±16 bb/100 avec 30 000 mains. Pour montrer
  une victoire de l'ordre de +7 bb/100 contre TAG, il faudrait environ 150 000 à 200 000 mains, ou des
  donnes dupliquées.

## Tests exécutés

```bash
.venv/bin/python -m pytest -q
cd frontend && npm test && npm run build
PB_BASE_URL=http://127.0.0.1:8097 node tests/cfr-room.mjs
PB_BASE_URL=http://127.0.0.1:8097 node tests/spectate.mjs
```

- **685 tests Python réussis** (668 hérités de la mission 4 et 17 nouveaux), **26 tests frontend
  réussis**, compilation réussie, et **2 tests navigateur réels** (table humain contre CFR, spectateur).
- Un seul test existant a été modifié, volontairement : la liste des modèles de salle contient désormais
  les politiques CFR.
- Audit des benchmarks : chaque décision CFR des 36 expériences (3 × 12) a été rejouée depuis sa graine
  et reproduite à l'identique, sans carte adverse dans les observations. Le rake recalculé main par main
  est identique.

## Reproduction

```bash
cd backend
../.venv/bin/python -m pokerbench.selfplay holdem --version 2 --iterations 300000 --seed 72001 \
  --every 10000 --snapshot 100000 --snapshot 200000 --output ../artifacts/repro/v2-72001
../.venv/bin/python -m pokerbench.mission5 run --workers 4 --output ../artifacts/repro/eval
../.venv/bin/python -m pokerbench.mission5 analyze ../artifacts/repro/eval --output ../artifacts/repro/eval/analysis.json
../.venv/bin/python -m pokerbench.mission5 run --confirm --workers 4 --output ../artifacts/repro/confirm
../.venv/bin/python -m pokerbench.mission5 analyze ../artifacts/repro/confirm --confirm --output ../artifacts/repro/confirm/analysis.json
```

**Versionné** : code, tests, politiques V2 (`artifacts/mission5/policy-v2-*.json.gz`), courbes
d'entraînement, plans, manifestes, `hands.csv` et `analysis.json` des trois évaluations
(`eval` préenregistrée, `eval-fixed`, `eval-confirm`). **Non versionné** : les journaux privés
`decisions.jsonl`, qui contiennent les cartes de chaque acteur. Aucun secret.

## Limites

- Aucune politique ne bat TAG de façon démontrée.
- L'abstraction reste grossière (mémoire imparfaite, une seule taille face à une relance). Ce n'est pas
  une stratégie GTO du no-limit complet, et aucune exploitabilité n'est mesurée dans le jeu réel.
- Le bug d'ordre des tailles a d'abord échappé aux tests ; il a été trouvé par l'évaluation elle-même.
- La table et le spectateur fonctionnent sur l'application locale ; aucun déploiement public n'a été fait
  dans cette mission.

## Suite proposée (mission 6)

1. **Donnes dupliquées** (mêmes cartes, positions échangées) pour diviser la variance et trancher
   enfin contre TAG.
2. **Entraînement plus long de V2** (1 million d'itérations), avec une courbe d'apprentissage à au moins
   5 instantanés évalués.
3. **Best response locale (LBR)** pour mesurer l'exploitabilité réelle de V1 et V2.
4. Une deuxième taille de relance face à une mise, et une mémoire des groupes des streets précédentes.
5. Déploiement de la table CFR sur le serveur public existant, après revue de sécurité.

Aucune intégration à des sites de poker tiers.
