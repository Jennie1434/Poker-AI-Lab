# Mission 4 — première IA de poker entraînable (CFR / self-play)

Documents relus avant les changements : `MISSION_3.md`, `MISSION_3_ETAT.md`,
`BENCHMARK_LAB.md`, `AUDIT_POKER_AI_LAB.md`. Le projet existant est réutilisé :
interface `Agent.choose_action(observation)`, pont serveur `play_action`,
benchmark `pokerbench.benchmark`, rake et statistiques de la mission 3. PokerKit
reste l'unique autorité sur les cartes, les actions légales et les gains.

## Synthèse

**L'agent CFR apprend réellement, progresse avec l'entraînement, joue des mains complètes
de Hold'em et bat trois des quatre agents de référence. Il ne bat pas encore
TightAggressiveAgent : le résultat est non concluant, avec une estimation légèrement
négative.**

| Question | Réponse mesurée |
| --- | --- |
| Apprend-il par self-play ? | **Oui.** Kuhn : exploitabilité 0,00001 et valeur −1/18 exacte. Leduc : 0,00026 et valeur −0,0856 publiée retrouvée. Aucune règle de jeu n'est programmée : la stratégie vient uniquement du self-play. |
| Progresse-t-il avec l'entraînement ? | **Oui.** En Hold'em, la politique à 200 000 itérations gagne **+199 bb/100 [+85 ; +314]** de plus que celle à 20 000 contre Equity, sur les mêmes 10 000 mains. Contre TAG : +34 bb/100 [−4 ; +73], amélioration probable mais non significative. |
| Joue-t-il au Texas Hold'em ? | **Oui, des mains réelles complètes** dans PokerKit (préflop à river, all-in, 200 BB), en raisonnant dans une **abstraction** (8 groupes de mains, relance pot ou all-in). Ce n'est **pas** une stratégie GTO du no-limit complet. |
| Bat-il TightAggressive ? | **Non démontré.** −9,60 bb/100 nets [−27,32 ; +8,12] sur 30 000 mains (rake 5 %) ; graines −14,3 / +1,2 / −15,7. Verdict préenregistré : **non concluant**. |

Résultats principaux (rake 5 %, plafond 3 BB, no-flop-no-drop ; 3 graines × 10 000 mains
par adversaire, graines jamais utilisées à l'entraînement) :

| Adversaire | bb/100 net CFR [IC 95 %] | Verdict préenregistré | Pour comparaison, mission 3 |
| --- | ---: | --- | --- |
| RandomAgent | **+565,72** [+501,44 ; +630,01] | bat | — |
| HeuristicAgent | **+52,11** [+51,28 ; +52,95] | bat | TAG : +2,66 ; Equity : +44,32 |
| EquityHeuristicAgent | **+172,13** [+125,88 ; +218,38] | bat | TAG : +155,64 |
| TightAggressiveAgent | **−9,60** [−27,32 ; +8,12] | non concluant | Equity : −187,83 |

Les comparaisons avec la mission 3 portent sur d'autres graines et ne sont pas
appariées : elles situent les ordres de grandeur, sans test formel. **Ces résultats
sont des simulations entre bots ; ils ne constituent ni une mesure d'exploitabilité
dans le jeu réel, ni une promesse de gain contre des humains.**

## Ordre de livraison

Les étapes ont été validées et poussées séparément, dans l'ordre demandé :

| Commit | Contenu | Validation |
| --- | --- | --- |
| `9eb2872` | CFR, CFR+ et MCCFR ; Kuhn et Leduc ; best response exacte ; checkpoints | 16 tests, 659 tests Python au total |
| `f7cb985` | Abstraction Hold'em, `CFRAgent`, entraînement, **protocole d'évaluation figé** | 668 tests Python au total |
| (dernier commit) | Entraînement, benchmark, analyse et rapport | voir « Tests exécutés » |

Le protocole d'évaluation Hold'em (graines, adversaires, tailles, rake, règle de
verdict) a été commité dans `backend/pokerbench/mission4.py` **avant** qu'une seule
main d'évaluation soit jouée.

## 1. CFR sur Kuhn Poker

`backend/pokerbench/cfr.py` implémente, pour tout jeu à deux joueurs à somme nulle :

- **CFR vanilla** (Zinkevich et al., 2007) : regret matching, mises à jour simultanées ;
- **CFR+** (Tammelin, 2014) : mises à jour alternées, regrets planchers à zéro,
  moyenne pondérée linéairement ;
- **MCCFR external sampling** (Lanctot et al., 2009) : hasard et adversaire échantillonnés,
  pour les jeux trop grands pour être parcourus ;
- **best response exacte** et **exploitabilité** = (BR₀ + BR₁) / 2, nulle exactement
  à un équilibre de Nash, exprimée en unités du jeu (jetons) par partie.

Correctif apporté pendant la validation : la première version modifiait les regrets
d'un ensemble d'information pendant l'itération, alors que d'autres histoires du même
ensemble étaient encore évaluées. CFR+ convergeait alors moins vite que CFR vanilla,
ce qui est un signe de bug. Les mises à jour sont désormais appliquées en fin de passe.

La best response a été validée indépendamment de l'entraînement : sur la famille
d'équilibres analytique de Kuhn (paramètre α ∈ {0, 1/6, 1/3}), l'exploitabilité
calculée vaut 0 à 10⁻¹² près et la valeur −1/18.

Résultats (`artifacts/mission4/toy/*/convergence.csv`, graine 7101) :

| Méthode | 100 it. | 1 000 it. | 10 000 it. | Valeur J1 finale | CPU |
| --- | ---: | ---: | ---: | ---: | ---: |
| CFR vanilla | 0,02567 | 0,00727 | 0,00232 | −0,05555 | 1,4 s |
| CFR+ | 0,00119 | 0,00009 | **0,00001** | **−0,05556** | 2,5 s |
| MCCFR external sampling | — | 0,01845 | 0,00629 (0,00104 à 100 000 it.) | −0,05550 | 3,0 s |

Valeur théorique : −1/18 = −0,05556. La stratégie CFR+ retrouve la structure connue
de l'équilibre : le joueur 1 bluffe le Valet avec une fréquence α ≤ 1/3, mise le Roi
avec 3α, ne mise jamais la Dame d'entrée et la paie avec α + 1/3 ; le joueur 2 bluffe
le Valet à 1/3 après un check. Ces propriétés sont vérifiées par les tests.

## 2. Leduc Poker

`backend/pokerbench/toy_games.py` : six cartes (J, Q, K en deux couleurs), ante 1,
relances de 2 puis 4, deux relances au maximum par tour, carte publique après le
premier tour. Une paire avec la carte publique gagne, sinon la carte la plus haute ;
égalité de rang = partage.

Un ensemble d'information contient **uniquement** le rang de la carte du joueur actif,
la carte publique si elle est révélée et **tout l'historique public des actions, tour
par tour** (`K Q:rc/cr`, par exemple). Les ranges sont donc conditionnées par les
actions : la stratégie dépend de la séquence de mises observée. Un test parcourt
tout l'arbre et vérifie que la clé ne change jamais quand seule la carte adverse
change. On obtient 288 ensembles d'information (couleurs isomorphes).

| Méthode | Itérations | Exploitabilité | Valeur J1 | CPU |
| --- | ---: | ---: | ---: | ---: |
| CFR vanilla | 1 000 | 0,0398 | −0,0912 | 55 s |
| CFR+ | 100 | 0,0134 | −0,0846 | — |
| CFR+ | 1 000 | **0,00026** | **−0,08559** | 96 s |
| MCCFR external sampling | 100 000 | 0,0415 | — | — |
| MCCFR external sampling | 500 000 | 0,0195 | −0,0877 | 110 s |

Valeur publiée de Leduc pour le premier joueur : environ −0,0856. CFR+ la retrouve
à 10⁻⁴ près. **Le MCCFR échantillonné, utilisé ensuite sur Hold'em, converge aussi**,
plus lentement par itération, mais chaque itération coûte environ 400 fois moins (0,2 ms contre 96 ms, mesures de convergence comprises).
C'est cette validation qui autorise son emploi sur un jeu où l'exploitabilité exacte
n'est plus calculable.

## 3. Abstraction heads-up Texas Hold'em

`backend/pokerbench/holdem_abstraction.py`, jeu `holdem-hu-abstract-v1`. Le format
reproduit celui du benchmark : 200 BB par joueur, réinitialisés à chaque main,
blinds 0,5/1 BB, unité de 50 jetons, sans ante.

| Dimension | Choix |
| --- | --- |
| Actions | fold, check/call, relance au pot `r`, all-in `a` |
| Profondeur | au plus 2 relances au pot et 3 relances (all-in compris) par street |
| Cartes préflop | 169 classes regroupées en 8 groupes par quantiles pondérés par combinaisons (≈ 166 combinaisons chacun), selon l'équité contre une main aléatoire (4 000 tirages par classe, graine fixe) |
| Cartes postflop | 8 groupes d'équité de largeur égale ; équité Monte Carlo à 32 tirages contre une main aléatoire |
| Mémoire | imparfaite pour les cartes : la clé contient le groupe de la street courante, la position et **tout l'historique abstrait des actions** |
| Position | joueur 0 = bouton/SB, joueur 1 = BB, comme dans PokerKit en heads-up |

La relance au pot reproduit exactement une des tailles proposées par le moteur :
3 BB pour l'ouverture, 3× la mise adverse pour une relance préflop, le pot entier
postflop. Un test fait jouer 120 mains réelles en parallèle dans PokerKit et dans
l'arbre abstrait, avec des actions abstraites aléatoires (all-in et relances multiples
inclus). Il vérifie à chaque décision que le joueur actif, la street, l'historique et
les jetons engagés sont identiques.

### Limites de l'abstraction (à lire avant tout chiffre)

1. **Ce n'est pas une stratégie GTO du no-limit complet.** La convergence est celle du
   MCCFR dans le jeu abstrait. Aucune exploitabilité n'est calculable dans le jeu réel,
   et l'abstraction elle-même est exploitable.
2. **Mémoire imparfaite des cartes** : l'agent oublie dans quel groupe était sa main
   aux streets précédentes. Les garanties de convergence du CFR supposent une mémoire
   parfaite ; elles ne s'appliquent donc pas formellement ici.
3. **Groupes fondés sur l'équité contre une main uniforme**, le défaut identifié en
   mission 3. La différence est que la stratégie CFR est conditionnée par l'historique
   des actions : une même force de main peut être jouée différemment après deux
   relances. La force du tirage (potentiel) n'est pas distinguée d'une main faite de
   même équité.
4. **Bruit d'estimation** : 32 tirages donnent une erreur type d'environ 9 points
   d'équité, donc souvent un groupe d'écart.
5. **Traduction des actions adverses** : toute relance réelle non all-in est lue comme
   `r`, quelle que soit sa taille. Au-delà des plafonds de profondeur, ou pour une
   combinaison jamais visitée à l'entraînement, l'agent sort de l'arbre et applique une
   règle de repli explicite : check si possible, call avec un groupe ≥ 5 sur 8, sinon
   fold. Le taux de repli est mesuré.
6. **Tailles de mise** : une seule taille de relance (pot) en plus de l'all-in ; pas de
   petites mises ni de surmises.
7. **Rake** : l'entraînement est sans rake (jeu à somme nulle). Le rake n'intervient
   qu'à l'évaluation, sans adaptation stratégique.

## 4. Checkpoints, reproductibilité et séparation entraînement / évaluation

- **Checkpoint d'entraînement** (`checkpoint.json`) : regrets, sommes de stratégie, actions
  par ensemble, nombre d'itérations, état complet du générateur aléatoire et métadonnées
  (abstraction, table préflop), avec une empreinte SHA-256. Le chargement refuse un
  fichier altéré, un autre jeu ou l'écrasement d'un fichier existant. **Reprendre un
  entraînement depuis un checkpoint donne exactement le même état** qu'un entraînement
  continu (testé pour CFR+, MCCFR et Hold'em).
- **Politique gelée** (`policy*.json.gz`) : stratégie moyenne arrondie à 10⁻⁴ et
  abstraction complète, avec sa propre empreinte. C'est le seul fichier lu en évaluation.
  `CFRAgent` ne contient aucun code d'apprentissage.
- **Graines** : entraînement Hold'em 71001 ; évaluation sur les couples (51001, 61001),
  (51002, 61002), (51003, 61003), jamais utilisés en entraînement ni dans les missions
  précédentes (vérifié par un test). Le hasard de l'agent vient uniquement de sa graine
  de politique, séparée de celle du paquet.
- **Self-play configurable** : `python -m pokerbench.selfplay toy|holdem` (jeu, variante,
  itérations, graine, fréquence des checkpoints, instantanés, reprise, nombre de tirages
  postflop).

## 5. Intégration à l'interface commune

`CFRAgent` implémente `choose_action(observation)` comme les autres agents. Il est
sélectionnable dans le benchmark via `--agent-a cfr --cfr-policy <fichier>`. L'empreinte de
la politique est enregistrée dans le manifeste de chaque expérience. L'agent lit
uniquement ses propres cartes, le board public et l'historique public de l'observation
filtrée. Le pont `play_action` lui transmet une copie et refuse toute action illégale ou
périmée. Un test vérifie que remplacer les cartes adverses dans l'observation ne change
aucune décision. L'audit de la mission 4 vérifie en outre, pour **chaque** décision CFR des
benchmarks, l'absence de carte adverse et la reproduction exacte de l'action à partir de la
graine.

## 6. Entraînement self-play Hold'em

```bash
cd backend
../.venv/bin/python -m pokerbench.selfplay holdem --iterations 200000 --seed 71001 \
  --every 10000 --snapshot 20000 --output ../artifacts/mission4/holdem-train-71001
```

- MCCFR external sampling, 200 000 itérations, **2 452 s CPU (41 min) sur un cœur**.
- 7 889 ensembles d'information visités à 10 000 itérations, 8 063 à 200 000 : l'arbre
  abstrait est presque entièrement couvert dès le début ; l'entraînement affine ensuite
  les fréquences.
- Le regret positif moyen par itération passe de 0,0176 (10 000 it.) à 0,0017 (200 000 it.).
  C'est un **indicateur de convergence dans le jeu abstrait**, pas une exploitabilité.
- Politiques gelées : `artifacts/mission4/policy-71001-200000.json.gz` (85 Ko) et
  `policy-71001-20000.json.gz` (81 Ko). Le checkpoint complet permet de reprendre
  l'entraînement.

## 7. Benchmark préenregistré

Plan exécuté sans modification (`artifacts/mission4/eval/plan.json`) :
`python -m pokerbench.mission4 run --workers 4`. Il comprend 12 expériences
principales de 10 000 mains (120 000 mains) et 2 diagnostics de 10 000 mains
(20 000 mains), soit **140 000 mains**. Chaque expérience alterne exactement le
bouton. Aucune expérience n'a été arrêtée, remplacée ni rejouée.

**Audit** (`mission4 analyze`) : empreintes de tous les fichiers, alternance des
positions et rake recalculé main par main. **Les 292 995 décisions CFR des 14
expériences ont été rejouées depuis leur graine et reproduites à l'identique**,
sans aucune carte adverse dans les observations.

### Résultats par graine (rake 5 %)

| Adversaire | 51001 | 51002 | 51003 | Écart-type des 3 moyennes |
| --- | ---: | ---: | ---: | ---: |
| Random | +557,44 [+445,29 ; +669,58] | +604,59 [+493,39 ; +715,80] | +535,14 [+424,44 ; +645,84] | 35,46 |
| Heuristic | +51,74 [+50,30 ; +53,18] | +52,78 [+51,34 ; +54,22] | +51,82 [+50,37 ; +53,28] | 0,58 |
| Equity | +183,59 [+103,21 ; +263,97] | +200,35 [+120,26 ; +280,45] | +132,45 [+52,60 ; +212,30] | 35,37 |
| TAG | −14,31 [−45,80 ; +17,19] | +1,21 [−27,98 ; +30,41] | −15,70 [−47,03 ; +15,63] | 9,39 |

### Sensibilité au rake (30 000 mains par adversaire, plafond 3 BB)

| Adversaire | 0 % | 2 % | 5 % | 7 % | Écart-type (BB/main) |
| --- | ---: | ---: | ---: | ---: | ---: |
| Random | +590,65 [525,65 ; 655,65] | +568,12 [503,83 ; 632,42] | +565,72 [501,44 ; 630,01] | +564,87 [500,58 ; 629,15] | 56,9 |
| Heuristic | +56,46 [55,60 ; 57,32] | +54,72 [53,87 ; 55,57] | +52,11 [51,28 ; 52,95] | +50,37 [49,55 ; 51,20] | 0,7 |
| Equity | +196,79 [150,09 ; 243,50] | +181,80 [135,53 ; 228,07] | +172,13 [125,88 ; 218,38] | +166,67 [120,43 ; 212,91] | 40,9 |
| TAG | −3,48 [−21,36 ; +14,39] | −6,70 [−24,45 ; +11,05] | −9,60 [−27,32 ; +8,12] | −11,18 [−28,89 ; +6,53] | 15,7 |

Contre TAG, l'IC contient zéro à tous les taux, **y compris sans rake** : le rake
n'explique pas l'absence de victoire. Contre les trois autres, la victoire résiste à
7 %. Le rake total prélevé contre TAG est de 3 849,5 BB à 5 %, contre 13 376,6 BB
contre Equity (pots plus gros).

### Progression avec l'entraînement (diagnostic apparié, graine 51001)

| Adversaire | Politique à 20 000 it. | Politique à 200 000 it. | Différence appariée [IC 95 %] |
| --- | ---: | ---: | ---: |
| Equity | −15,62 [−144,32 ; +113,08] | +183,59 [+103,21 ; +263,97] | **+199,21 [+84,60 ; +313,82]** |
| TAG | **−48,55 [−84,91 ; −12,18]** | −14,31 [−45,80 ; +17,19] | +34,24 [−4,32 ; +72,80] |

À 20 000 itérations, l'agent **perdait significativement** contre TAG et ne battait pas
Equity. Dix fois plus d'entraînement le rend nettement gagnant contre Equity et ramène son
résultat contre TAG près de l'équilibre. C'est la preuve mesurée que le self-play
améliore le jeu réel, sur une seule graine et deux points de la courbe d'apprentissage.

### Coût de calcul

| Agent | CPU par décision (pont moteur inclus) |
| --- | ---: |
| CFRAgent | **1,0 à 1,8 ms** |
| TightAggressiveAgent | 3,6 à 3,9 ms |
| EquityHeuristicAgent | 8,3 à 9,8 ms |

L'agent CFR est le plus rapide des agents « réfléchis » : la stratégie est précalculée ;
seule l'estimation du groupe postflop (32 tirages) coûte à l'exécution. Le coût est
reporté sur l'entraînement (41 min CPU).

### Sorties de l'arbre abstrait

| Adversaire | Décisions CFR | Taux de repli |
| --- | ---: | ---: |
| Heuristic | 66 877 | 0,00 % |
| TAG | 35 194 | 0,16 % |
| Equity | 92 906 | 2,8 % |
| Random | 61 699 | 7,0 % |

Les replis viennent surtout des séquences de relances que l'abstraction ne contient pas
(Random relance dans 71 % de ses décisions préflop). Contre TAG, ils sont négligeables : **le résultat contre
TAG reflète bien la stratégie apprise, pas la règle de repli.**

### Pourquoi TAG résiste (fréquences sur 30 000 mains)

| Agent (adversaire) | VPIP | PFR | Fold BB face à relance | Fold face à mise postflop | bb/100 bouton | bb/100 BB |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| CFR (TAG) | 43,5 % | 22,1 % | 51,8 % | 50,4 % | −8,3 | −10,9 |
| TAG (CFR) | 19,4 % | 16,0 % | 78,0 % | 64,1 % | +4,0 | −10,5 |
| CFR (Equity) | 50,9 % | 31,5 % | 53,0 % | 51,2 % | +194,3 | +150,0 |
| Equity (CFR) | 68,6 % | 8,3 % | 11,8 % | 36,2 % | −194,1 | −239,3 |

L'agent CFR gagne 71,3 % des mains contre TAG, mais il les gagne petites, surtout par
des vols de blindes : TAG abandonne sa BB 78 % du temps. Il perd les gros pots, où TAG
n'engage que des mains fortes. Contre Equity, qui paie presque tout (VPIP 68,6 %,
PFR 8,3 %), la même stratégie rapporte beaucoup. **Une stratégie d'équilibre abstrait
est robuste mais n'exploite pas activement un adversaire très serré**, et l'abstraction
ne dispose ni de petites mises ni de surmises pour mieux valoriser ses mains.

## Tests exécutés

```bash
.venv/bin/python -m pytest -q backend/tests/test_cfr.py backend/tests/test_holdem_abstraction.py backend/tests/test_mission4.py
.venv/bin/python -m pytest -q
cd frontend && npm test && npm run build
```

**668 tests Python réussis** (643 hérités de la mission 3 + 25 nouveaux), **26 tests frontend
réussis**, compilation TypeScript/Vite réussie.

Tests ajoutés pour la mission 4 (25) :

- **CFR** : regret matching ; best response certifiant les équilibres analytiques de Kuhn
  (α = 0, 1/6, 1/3) ; punition d'une stratégie non équilibrée ; convergence de CFR, CFR+
  et MCCFR ; structure de l'équilibre de Kuhn retrouvée ; Leduc à la valeur publiée.
- **Leduc** : règles et gains, nombre d'ensembles d'information, et clé indépendante de la
  carte adverse sur tout l'arbre.
- **Checkpoints** : reprise identique à l'entraînement continu (CFR+, MCCFR, Hold'em,
  générateur aléatoire compris) ; refus d'un fichier altéré, d'un autre jeu et de
  l'écrasement.
- **Hold'em** : classes et groupes préflop équilibrés ; jeu abstrait borné et à somme
  nulle ; **cohérence jeton par jeton avec PokerKit** sur 120 mains ; indépendance vis-à-vis
  des cartes cachées ; repli compté ; intégrité de la politique ; mains de benchmark
  complètes.
- **Protocole** : graines nouvelles et tailles fixées ; analyse de bout en bout sur un
  mini-plan ; audit détectant une décision falsifiée même avec empreinte recalculée.

## Reproduction

```bash
cd backend
# Kuhn / Leduc (exploitabilité exacte)
../.venv/bin/python -m pokerbench.selfplay toy --game leduc --variant plus --iterations 1000 \
  --every 50 --seed 7101 --output ../artifacts/repro/leduc-plus
# Hold'em : entraînement, puis benchmark préenregistré et analyse
../.venv/bin/python -m pokerbench.selfplay holdem --iterations 200000 --seed 71001 \
  --every 10000 --snapshot 20000 --output ../artifacts/repro/holdem
../.venv/bin/python -m pokerbench.mission4 run --workers 4 --output ../artifacts/repro/eval
../.venv/bin/python -m pokerbench.mission4 analyze ../artifacts/repro/eval \
  --output ../artifacts/repro/eval/analysis.json
# Une confrontation isolée avec la politique versionnée
../.venv/bin/python -m pokerbench.benchmark --hands 10000 --agent-a cfr --agent-b tag \
  --cfr-policy artifacts/mission4/policy-71001-200000.json.gz --deck-seed 51001 \
  --policy-seed 61001 --measure-time --output ../artifacts/repro/single
```

`mission4 run` lit les politiques aux chemins du protocole (relatifs à la racine du dépôt) ;
leurs empreintes sont dans `plan.json` et dans chaque manifeste.

**Versionné dans Git** : code, tests, politiques gelées et checkpoint d'entraînement,
courbes de convergence Kuhn/Leduc, `plan.json`, manifestes, `hands.csv`, `analysis.json`
et `frequencies.json`. **Non versionné** : les `decisions.jsonl` (≈ 1,1 Go au total), qui
sont des journaux privés contenant les cartes de chaque acteur. `mission4 run` les régénère.
Aucun secret ni fichier `.env` n'est inclus.

## Limites

- Abstraction grossière (section 3) ; aucune exploitabilité mesurée dans le jeu réel.
- Un seul entraînement (graine 71001) : la variance entre entraînements n'est pas mesurée.
- Courbe d'apprentissage à deux points (20 000 et 200 000 itérations), sur une graine.
- Adversaires de référence à règles fixes ; aucune évaluation contre des humains ou contre
  Jev (non connecté dans cette mission).
- Stacks réinitialisés à chaque main ; rake sans adaptation stratégique.
- L'agent n'est pas encore branché dans les salles web humain contre IA.

## Suite à donner (mission 5 proposée)

1. **Battre TAG de façon significative** : ajouter des tailles de mise (½ pot, 2× pot), des
   groupes de mains tenant compte du potentiel (tirages) et la mémoire parfaite des groupes,
   puis réentraîner plus longtemps.
2. **Mesurer l'exploitabilité réelle** par une best response locale (LBR) dans le jeu réel,
   au lieu de seulement jouer contre des bots.
3. **Courbe d'apprentissage complète** (5 instantanés au moins) et **plusieurs graines
   d'entraînement**.
4. **Réduire la variance** de l'évaluation par donnes dupliquées (mêmes cartes, positions
   échangées) : l'IC contre TAG fait encore ±18 bb/100 avec 30 000 mains.
5. **Brancher `CFRAgent` dans les salles privées humain contre IA** existantes, derrière une
   configuration serveur, avec les tests de bout en bout prévus dans l'audit.
6. Envisager un module d'exploitation de l'adversaire en complément de l'équilibre, et un
   entraînement tenant compte du rake.

Aucune connexion Jev, aucun site tiers et aucune automatisation de plateforme de poker n'ont
été intégrés.
