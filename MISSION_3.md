# Mission 3 — évaluation de la force réelle des agents

Rapport final. Mission commencée dans Codex (protocole, TightAggressiveAgent, audit,
calculs), puis terminée dans Claude Code (rejeu de contrôle, agrégation, rake,
sensibilité 64/256/1024, fréquences, tests de l'analyse et synthèse). L'état exact
au moment de la reprise est conservé dans `MISSION_3_ETAT.md`.

## Synthèse

**Réponse à la question posée : non, EquityHeuristicAgent n'est pas compétitif.**
Sa victoire de la mission 2 tenait à la faiblesse d'un adversaire aléatoire.

| Confrontation (3 graines × 10 000 mains) | bb/100 net du premier agent, rake 5 % [IC 95 %] | Lecture |
| --- | ---: | --- |
| Equity vs TightAggressive | **−187,83** [−209,55 ; −166,11] | perte nette, très nette sur les 3 graines |
| Equity vs Heuristic simple | **+44,32** [+41,94 ; +46,71] | gain contre un joueur qui ne mise jamais |
| TightAggressive vs Heuristic simple | **+2,66** [+1,77 ; +3,56] | gain faible mais positif, même à 7 % de rake |

- Les 3 graines indépendantes donnent toutes le même signe ; l'écart-type entre graines
  (9,1 bb/100 pour Equity/TAG) est plus faible que la demi-largeur de l'IC.
- La perte contre le TAG **ne vient pas du rake** : elle vaut déjà −177,03 bb/100 à 0 %.
- Le principal défaut identifié est l'**estimation contre une main uniforme** : sur un échantillon
  river non sélectionné, Equity s'attribue 54,7 % d'équité alors que sa part réelle au
  showdown est de 16,0 % (écart de 38,7 points).
- **Plus de simulations n'améliorent pas le résultat** : à 256 et 1024 tirages, Equity
  perd ~46–48 bb/100 de plus qu'à 64 sur les mêmes 1 000 mains, pour un coût
  par décision 1,6× à 4,4× plus élevé. Une estimation plus précise d'une
  quantité mal définie (range uniforme) ne corrige pas le biais.
- Ces résultats sont des simulations entre bots à stacks réinitialisés : **ils ne
  constituent ni une mesure d'exploitabilité, ni une promesse de rentabilité réelle**.

## Reprise et contrôle d'intégrité

Les 12 journaux de décisions de plus de 50 Mo n'avaient pas pu être poussés sur GitHub
par Codex. Toutes les expériences ont donc été rejouées depuis le plan enregistré
(`mission3 run --workers 4 --output artifacts/mission3-reprise`) :

- les **11 `hands.csv` régénérés sont identiques octet par octet** à ceux de Codex ;
- les **22 empreintes SHA-256** (`hands.csv` et `decisions.jsonl`) correspondent à celles des
  manifestes Codex ;
- `analyze` a ensuite revérifié ces empreintes, l'alternance des positions et, main par main,
  que le recalcul indépendant du rake à 5 % reproduit exactement les gains nets enregistrés.

Les résultats sont donc reproductibles, et les journaux manquants sont restaurés à
l'identique (localement, hors Git, car ils contiennent les cartes privées de chaque acteur).
`artifacts/mission3/analysis.json`, `analysis.csv` et `frequencies.json` proviennent de
cette exécution ; seuls les temps CPU de `runs[].runtime` sont ceux de la machine de reprise.

## Question et protocole fixé avant les résultats

La mission 2 montrait qu'EquityHeuristicAgent bat RandomAgent. Elle ne démontrait
pas une force générale au poker. La présente mission confronte trois politiques
fixes, sans entraînement, sans connexion fournisseur et sans site tiers.
`BENCHMARK_LAB.md` et `AUDIT_POKER_AI_LAB.md` ont été lus avant les changements.

Le plan exécutable est `pokerbench.mission3.jobs()` et sa copie enregistrée
`artifacts/mission3/plan.json`. Les trois couples indépendants de graines
(paquet, politiques) sont **(31001, 41001), (31002, 41002), (31003, 41003)**.
Pour chaque couple :

- EquityHeuristicAgent contre TightAggressiveAgent : 10 000 mains ;
- EquityHeuristicAgent contre HeuristicAgent : 10 000 mains ;
- TightAggressiveAgent contre HeuristicAgent : 10 000 mains.

Soit **90 000 mains principales**, 30 000 par confrontation. Chaque expérience
alterne exactement 5 000 boutons/SB et 5 000 BB par siège. Les stacks sont
réinitialisés à 200 BB à chaque main, blinds 0,5/1 BB, sans ante. Les mêmes
couples de graines sont réutilisés entre confrontations : les expériences de
confrontations différentes sont donc corrélées, pas des réplications
indépendantes entre elles. Les RNG de paquet et de politique restent séparés,
avec dérivation SHA-256 par domaine et par main.

Budget fixé pour l'analyse secondaire : première tranche de **1 000 mains** du
premier Equity/TAG à 64 simulations, puis 1 000 mains aux mêmes graines à 256
et 1024. Le budget du TAG reste à 64 ; seul EquityHeuristicAgent change. Les
résultats de cette analyse ne sont pas présentés comme des confrontations
principales à 10 000 mains. Les différences sont appariées par bloc de deux
mains, sans supposer que les trajectoires ou le nombre de décisions restent
identiques. Aucun arrêt précoce n'est déclenché selon le résultat.

Les ressources détectées étaient 4 CPU de quota, environ 34 Go de RAM ; trois
processus d'expériences ont été utilisés. Un pilote de 100 mains Equity/TAG a
terminé en 2,41 s. Le pilote utilise des graines différentes et n'entre pas
dans les résultats principaux.

## Adversaire TightAggressiveAgent

L'agent est ajouté à `agents.py` et sélectionnable par `--agent-a tag` ou
`--agent-b tag`. Il réutilise exclusivement l'observation autorisée du joueur
actif. Le moteur PokerKit et ses règles sont inchangés.

Préflop, les classes sont explicites :

| Classe | Sélection |
| --- | --- |
| 4 | QQ+, AK |
| 3 | 99–JJ, AQ, AJs, KQs |
| 2 | autres paires, broadways J-high ou mieux avec deuxième carte >= T, autres as assortis, A9+ |
| 1 | connecteurs assortis 65s+ non déjà classés |
| 0 | autres mains |

Sur les 1 326 combinaisons, les classes 1–4 contiennent **302 combinaisons,
soit 22,78 %**. C'est une référence **très serrée pour du heads-up** : elle peut
être exploitée par des vols de blindes et ne représente pas un joueur expert.
Le bouton ouvre les classes 1–4 ; la BB peut isoler les classes 2–4 après limp.
Ouverture à environ 3 BB parmi les tailles proposées ; surrelance de valeur
pour les classes 3–4, sans escalade répétée. Les calls spéculatifs sont plafonnés
à 2/3 BB selon la classe, 10 BB pour la classe 3 ; les gros engagements
préflop sont réservés aux premiums.

Postflop, une estimation d'équité contre une main uniforme est complétée par
une marge de prudence augmentant avec les relances et le prix du call. Un call
engageant plus du quart du capital nécessite au moins 75 % d'équité estimée,
plus de la moitié au moins 85 %. Les mises de valeur visent deux tiers du pot
après call, avec une limite de capital et une seule relance propre par street.
Des semi-bluffs en position avec tirage sont tentés à 20 % ; des bluffs river
après check adverse à 8 %, sous conditions de faible équité et de risque.
Ces fréquences sont des règles fixes, pas une calibration d'équilibre.

Le TAG n'apprend pas de range adverse. Il partage l'estimation uniforme avec
EquityHeuristicAgent mais impose une sélection, des tailles de mise et des
limites de risque différentes. Battre ce TAG ne suffirait pas à démontrer une
force contre une politique équilibrée ou des humains.

## Audit de la mission 2

`pokerbench.mission3 audit` vérifie les checksums, reconstruit toutes les mains
par la graine du paquet et rejoue chaque action. Chaque observation complète
est comparée à `Hand.observation()` avant l'action, ainsi que l'acteur, le
compteur, les actions légales et la confidentialité. Après la main, les profits
sont recalculés indépendamment par `stack_final - stack_initial`, puis les pots,
le rake et les gains nets sont contrôlés.

Résultat : **20 000 mains et 101 378 décisions vérifiées**, aucune divergence
de cartes cachées, d'observation, d'action légale ou de profit détectée.
Les journaux complets restent privés : chacun contient les cartes propres des
différents acteurs à leurs tours. Leur réunion et les graines permettent de
reconstituer les donnes ; ils ne sont jamais fournis aux agents ou au tableau
public.

| Expérience | Décisions vérifiées | Mains comportant une action all-in | Profit net du siège étudié sur ces mains | Profit net sur les autres mains |
| --- | ---: | ---: | ---: | ---: |
| Random / Equity | 66 096 | 4 066 | +158 381,50 BB | +62 581,30 BB |
| Random / Heuristic | 35 282 | 2 164 | −2 790,50 BB | −8 725,70 BB |

Une « main all-in » inclut une mise all-in non suivie ; cela ne signifie pas
nécessairement un showdown all-in. Pour Equity contre Random, environ 71,7 %
du profit net provient de ces mains. Ce résultat dépend fortement des gros
engagements d'un adversaire aléatoire.

Sélection d'audit : les 20 plus gros pots gagnés et les 20 plus gros pots perdus
par Equity, et la même sélection pour Heuristic. Tri par pot disputé décroissant,
puis profit absolu, puis numéro de main ; de nombreux pots sont ex aequo à
400 BB. **Les politiques ont été réexécutées sur ces 80 mains**, retrouvant
chaque action. Les autres actions sont rejouées et validées, sans recalculer
chaque estimation Monte Carlo. Les 80 showdowns sélectionnés ont également
été évalués par Treys, indépendamment du règlement PokerKit : aucun désaccord
sur le gagnant. Les détails des décisions, montants et streets sont dans les
JSON d'audit, et les 40 mains d'Equity sont listées plus bas.

Cette validation porte sur ces jeux de données et ces chemins d'exécution ;
elle ne constitue pas une preuve générale d'absence de tout bug de sécurité.

## Statistiques et rake

Le score net est `100 * profit_net_en_BB / nombre_de_mains`.
Les IC à 95 % sont asymptotiques sur les moyennes de blocs indépendants de deux
mains (une par position), comme en mission 2. Les résultats par graine sont
conservés en plus de l'agrégation des 30 000 mains. L'écart-type des profits
**en BB par main** mesure leur dispersion ; il ne doit pas être confondu avec
l'erreur standard de la moyenne en bb/100. L'écart-type des trois moyennes par
graine est aussi exporté, mais trois réplications restent peu nombreuses.

Les quatre scénarios utilisent **0 %, 2 %, 5 %, 7 %, plafond 3 BB par main,
no-flop-no-drop**. Le prélèvement est arrondi au jeton entier, hors mise non
suivie, et réparti sur les gains du pot. `mission3.rerake` recalcule les gains
depuis le CSV, indépendamment de `settle_rake` ; le scénario 5 % doit reproduire
exactement les gains nets enregistrés. Les autres taux utilisent les mêmes
mains et décisions : aucune adaptation stratégique au rake n'est simulée.
Les stacks étant réinitialisés, l'analyse n'est pas une simulation de bankroll
persistante. À 0 %, les résultats nets sont les résultats bruts.

Les IC ne sont pas corrigés pour toutes les comparaisons multiples. Les
résultats nets ne forment pas un jeu à somme nulle : les deux agents peuvent
perdre après rake. Les graines sont contrôlées et les échantillons indépendants
entre réplications, mais des tests sur quelques bots ne mesurent ni une
exploitabilité GTO, ni une rentabilité réelle garantie.

## Coût de 64, 256 et 1024 simulations

Un contrôle séparé utilise les 50 premières observations d'Equity par street
préflop/flop/turn/river du journal de mission 2, soit **200 états fixes**. Les
mêmes graines de politique sont utilisées pour chaque budget. L'échantillon
est descriptif et non aléatoire, équilibré par street, pas par fréquence réelle
d'apparition. La latence mesurée est du temps CPU, non une garantie de latence
réseau ou de machine utilisateur.

| Simulations | CPU moyen par décision | CPU médian | Décisions différentes de 64 |
| ---: | ---: | ---: | ---: |
| 64 | 4,99 ms | 4,53 ms | — |
| 256 | 8,76 ms | 8,15 ms | 19 / 200 (9,5 %) |
| 1024 | 24,48 ms | 23,18 ms | 20 / 200 (10 %) |

Le coût inclut la création de l'évaluateur à chaque décision, ce qui explique
qu'il ne soit pas strictement proportionnel au nombre de tirages. Le taux de
changement n'est pas un taux d'erreur : 1024 n'est pas une vérité de référence,
et une estimation précise contre la mauvaise range reste biaisée.
Le protocole de partie exporte également les secondes CPU et les nombres de
décisions par siège ; ce chronométrage inclut le pont de validation/applique du
moteur, contrairement au contrôle ci-dessus qui ne mesure que la politique.

## Résultats mesurés

Toutes les valeurs sont en bb/100 nets, sauf indication. IC à 95 % asymptotiques sur les
blocs indépendants de deux mains (une main par position). Écart-type exprimé **en BB par
main** (dispersion), distinct de l'erreur standard.

### Résultats par graine (rake 5 %, plafond 3 BB, no-flop-no-drop)

| Confrontation | Graine 31001 | Graine 31002 | Graine 31003 | Écart-type des 3 moyennes |
| --- | ---: | ---: | ---: | ---: |
| Equity vs TAG (Equity) | −184,37 [−222,30 ; −146,45] | −180,95 [−218,81 ; −143,10] | −198,16 [−235,23 ; −161,09] | 9,11 |
| Equity vs Heuristic (Equity) | +43,09 [+38,93 ; +47,25] | +46,14 [+42,04 ; +50,24] | +43,74 [+39,59 ; +47,89] | 1,61 |
| TAG vs Heuristic (TAG) | +1,88 [+0,30 ; +3,46] | +2,05 [+0,53 ; +3,57] | +4,06 [+2,51 ; +5,61] | 1,21 |

Chaque expérience comporte exactement 5 000 mains au bouton et 5 000 en BB par siège.
Les confrontations partagent les mêmes couples de graines ; elles sont donc corrélées entre
elles, alors que les trois graines sont des réplications indépendantes.

### Agrégat de 30 000 mains et sensibilité au rake

Plafond fixe de **3 BB par main** à tous les taux, no-flop-no-drop, mêmes mains et mêmes
décisions (aucune adaptation stratégique au rake n'est simulée).

| Confrontation | Siège | 0 % | 2 % | 5 % | 7 % | Écart-type (BB/main) |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Equity vs TAG | Equity | −177,03 [−198,95 ; −155,11] | −182,84 [−204,59 ; −161,08] | −187,83 [−209,55 ; −166,11] | −190,62 [−212,33 ; −168,91] | 19,0 |
| | TAG | +177,03 [155,11 ; 198,95] | +164,85 [143,33 ; 186,37] | +155,64 [134,21 ; 177,07] | +151,31 [129,90 ; 172,72] | |
| Equity vs Heuristic | Equity | +57,15 [54,59 ; 59,70] | +52,02 [49,53 ; 54,50] | +44,32 [41,94 ; 46,71] | +39,19 [36,87 ; 41,51] | 2,1 |
| | Heuristic | −57,15 [−59,70 ; −54,59] | −59,98 [−62,50 ; −57,46] | −64,23 [−66,70 ; −61,76] | −67,06 [−69,49 ; −64,63] | |
| TAG vs Heuristic | TAG | +4,71 [3,79 ; 5,62] | +3,89 [2,98 ; 4,80] | +2,66 [1,77 ; 3,56] | +1,85 [0,96 ; 2,73] | 0,8 |
| | Heuristic | −4,71 [−5,62 ; −3,79] | −5,46 [−6,36 ; −4,56] | −6,58 [−7,47 ; −5,70] | −7,33 [−8,21 ; −6,46] | |

Rake total prélevé sur les 30 000 mains, en BB :

| Confrontation | 2 % | 5 % | 7 % |
| --- | ---: | ---: | ---: |
| Equity vs TAG | 5 397,3 | 9 656,9 | 11 793,2 |
| Equity vs Heuristic | 2 388,6 | 5 971,4 | 8 360,0 |
| TAG vs Heuristic | 470,5 | 1 176,2 | 1 646,7 |

Lecture :

- À 0 %, le jeu est à somme nulle ; dès 2 %, les deux sièges paient et la somme des
  bb/100 devient négative.
- Le plafond de 3 BB limite fortement le coût : entre 5 % et 7 %, le rake prélevé n'augmente
  que d'environ 22 % sur Equity/TAG (gros pots plafonnés) contre 40 % sur Equity/Heuristic
  (pots moyens rarement plafonnés).
- **La marge du TAG contre l'heuristique simple (+4,71 à 0 %) est la plus sensible** :
  le rake à 7 % en retire 61 %. Un avantage de quelques bb/100 entre bots peut
  disparaître avec un rake réel plus élevé ou un plafond plus haut.
- Le classement des agents est le même aux quatre taux.

### Sensibilité au nombre de simulations d'équité

Diagnostic secondaire, fixé avant les résultats : 1 000 premières mains d'Equity/TAG à la
graine 31001, TAG fixé à 64 tirages, seul Equity varie. Les écarts sont appariés main par
main (blocs de deux mains). Ce n'est **pas** une confrontation principale.

| Tirages Equity | bb/100 net Equity (1 000 mains) | Écart apparié vs 64 [IC 95 %] | CPU par décision, moteur inclus | CPU par décision, politique seule (200 états fixes) | Décisions changées vs 64 (200 états) |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 64 | −144,50 [−263,15 ; −25,85] | — | 8,2 ms | 4,99 ms | — |
| 256 | −192,20 [−313,49 ; −70,91] | −47,70 [−83,75 ; −11,65] | 13,4 ms | 8,76 ms | 19 (9,5 %) |
| 1024 | −190,19 [−313,83 ; −66,56] | −45,70 [−83,47 ; −7,92] | 35,6 ms | 24,48 ms | 20 (10 %) |

Le CPU « moteur inclus » vient des manifestes de partie (pont de validation et
application PokerKit compris ; à 64 tirages, sur les 10 000 mains). Les intervalles
individuels sont très larges sur 1 000 mains ; seule la comparaison appariée est
informative. Elle indique que **plus de précision rend Equity légèrement pire** sur cette
graine, cohérent avec un biais de range : plus l'estimation uniforme est stable, plus
l'agent s'engage de façon cohérente avec une équité surestimée. Cette conclusion repose
sur une seule graine et 1 000 mains ; elle devra être répliquée. **Recommandation :
garder 64 tirages tant que le modèle de range n'est pas corrigé** ; le gain de calcul
est réel et l'augmentation n'apporte aucun bénéfice mesuré.

## Faiblesses d'EquityHeuristicAgent, mesurées

Fréquences agrégées sur les 3 graines (`artifacts/mission3/frequencies.json`).
VPIP = part des mains où l'agent met volontairement de l'argent préflop ; PFR = part des
mains où il relance préflop.

| Agent (adversaire) | VPIP | PFR | Fold de la BB face à une relance | Fold face à une mise postflop | bb/100 au bouton | bb/100 en BB |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Equity (TAG) | 59,5 % | 6,2 % | 11,3 % (3 387 cas) | 22,6 % | −209,1 | −166,6 |
| TAG (Equity) | 22,0 % | 21,2 % | 70,9 % (1 560 cas) | 21,8 % | +145,4 | +165,9 |
| Equity (Heuristic) | 54,1 % | 9,4 % | — (aucune relance subie) | — (aucune mise subie) | +44,9 | +43,8 |
| TAG (Heuristic) | 22,3 % | 22,3 % | — | — | −15,5 | +20,9 |
| Heuristic (TAG) | 50,0 % | 0,0 % | 100 % (3 445 cas) | 100 % | −28,7 | +15,5 |

Les bb/100 par position sont des moyennes simples des 3 graines, calculées sur 5 000
mains par position et par graine.

1. **Estimation des ranges (défaut principal).** L'équité est calculée contre une main
   uniforme même après une ou plusieurs relances. Sur 200 décisions river face à une mise,
   tirées sans regarder le résultat parmi 1 256 éligibles (graine 31001), l'équité uniforme
   moyenne est de 54,73 % contre une part réelle au showdown de 16,00 % : surestimation de
   **38,7 points** [34,7 ; 42,7]. Dans les 20 plus gros pots perdus, l'équité uniforme moyenne
   était de 83,0 % (sélection sur les pertes, indicative seulement).
2. **Préflop trop passif et trop large.** VPIP 59,5 % mais PFR 6,2 % contre le TAG :
   87 % de ses décisions préflop sont des calls (limps au bouton compris) et il n'abandonne
   la BB face à une relance que dans 11,3 % des cas. Il paie donc les ouvertures d'une range de 22,8 % des combinaisons avec
   une majorité de mains dominées.
3. **Défense des blindes et position.** Equity perd plus au bouton (−209,1) qu'en BB
   (−166,6) : il n'exploite pas la position. Il ne vole presque jamais les blindes alors que
   le TAG abandonne sa BB à 70,9 % face à une relance ; c'est un profit laissé sur la table.
4. **Relances.** Equity relance 24 % de ses décisions au flop, 26 % au turn et 32 % à la
   river. Les relances suivent un seuil d'équité uniforme et ignorent le message de
   l'agression adverse. Il n'a aucune limite de relances par street et aucune taille
   distincte pour la valeur et le bluff.
5. **Bluff.** Equity n'a aucune stratégie de bluff ou de semi-bluff explicite ; son
   agression vient uniquement de l'équité surestimée. Contre l'heuristique simple, aucune
   mise ne reçoit de fold (cet adversaire ne mise jamais et ne se couche jamais postflop),
   donc la fold equity n'y est pas testée.
6. **Postflop et risque.** Il paie avec des pot odds et une marge fixe, sans tenir compte du
   risque sur le tapis : 20 actions all-in contre le TAG (6 mains sur la graine 31001, toutes
   perdues : −1 200 BB). Cependant, l'essentiel de la perte (−17 237 BB sur cette graine) vient
   des autres mains, c'est-à-dire de l'accumulation de calls et de relances moyens contre
   une range forte.

Limites : ces fréquences sont descriptives. Attribuer causalement la perte à une règle
précise exigera des ablations préenregistrées (range adverse conditionnelle, table
d'ouverture, seuil de call, sizing) sur les mêmes graines.

Le TAG n'est pas non plus un joueur fort : sa marge contre l'heuristique simple est faible
(+2,66 bb/100 à 5 %) et il perd au bouton (−15,5) en abandonnant 39 % de ses décisions
préflop. Il sert de référence sélective, pas d'objectif.

## Reproduction

Depuis la racine du dépôt, avec des dossiers de sortie inexistants (aucune expérience n'est
écrasée). Les commandes `pokerbench.*` se lancent depuis `backend/`, ou avec
`PYTHONPATH=backend` :

```bash
cd backend
# Plan complet : 90 000 mains principales + 2 000 mains de sensibilité (≈ 25 min sur 4 CPU).
../.venv/bin/python -m pokerbench.mission3 run --workers 4 --output ../artifacts/mission3-reproduction
../.venv/bin/python -m pokerbench.mission3 analyze ../artifacts/mission3-reproduction \
  --output ../artifacts/mission3-reproduction/analysis.json
PYTHONPATH=. ../.venv/bin/python ../scripts/mission3_review.py frequencies \
  ../artifacts/mission3-reproduction ../artifacts/mission3-reproduction/frequencies.json

# Vérifier l'identité avec les résultats enregistrés.
for d in ../artifacts/mission3/*/; do cmp "$d/hands.csv" "../artifacts/mission3-reproduction/$(basename $d)/hands.csv"; done

# Audit des mains de la mission 2 et diagnostic de coût (nécessitent leurs decisions.jsonl).
mkdir -p ../artifacts/mission3-reproduction-audit
../.venv/bin/python -m pokerbench.mission3 audit ../artifacts/mission2/random-v-equity \
  --output ../artifacts/mission3-reproduction-audit/equity.json
../.venv/bin/python -m pokerbench.mission3 cost ../artifacts/mission2/random-v-equity \
  --output ../artifacts/mission3-reproduction-audit/cost.json
```

`analyze` refuse toute expérience incomplète, déséquilibrée en positions, dont un fichier
diffère de son empreinte ou dont le rake recalculé indépendamment ne reproduit pas les gains
nets. Un clone GitHub ne contient pas les `decisions.jsonl` principaux : il faut d'abord
relancer `run`, qui les régénère à l'identique. Les temps CPU varient selon la machine ; les
actions, profits et observations ne varient pas.

## Tests exécutés

```bash
.venv/bin/python -m pytest -q backend/tests/test_mission3.py   # 19 réussis
.venv/bin/python -m pytest -q                                   # 643 réussis
cd frontend && npm test && npm run build                        # 26 réussis, build OK
```

- **643 tests Python réussis** (641 hérités de Codex + 2 ajoutés à la reprise), **26 tests
  frontend réussis**, compilation TypeScript/Vite réussie.
- Tests de la mission 3 : classes préflop du TAG, défense de BB, rejet des all-in
  spéculatifs, seuils de risque postflop, détection des tirages, confidentialité et
  reproductibilité, détection par l'audit d'une observation falsifiée même avec empreinte
  recalculée, rake indépendant et monotone, tailles et graines du plan, unités des écarts-types.
- Ajoutés à la reprise : `analyze` exécuté sur un mini-plan réel (agrégation des 3 graines,
  rake 0 % = brut, 5 % = net enregistré, monotonie, diagnostic 64/256/1024, export CSV), et
  rejet d'un journal altéré ou manquant. Les tailles du plan sont devenues des constantes
  (`MAIN_HANDS`, `DIAGNOSTIC_HANDS`) pour permettre ce test, sans changer le plan.
- Vérifications sur les données complètes (en plus des tests) : 92 000 mains rejouées
  identiques à la reprise ; audits effectués par Codex sur 30 000 mains et 152 087 décisions
  (missions 2 et 3) et 120 showdowns contrôlés indépendamment avec Treys, sans divergence. PokerKit reste l'unique arbitre ;
  aucune observation d'agent ne contient de carte cachée adverse.

Non fait dans cette mission : tableau de bord visuel de la mission 3 (les résultats sont
dans `analysis.csv`), ablations causales des règles d'Equity, réplication multi-graines du
diagnostic 64/256/1024.

## Priorités pour l'agent CFR/self-play (Mission 4, non lancée)

1. **Modèle de range d'abord.** Le défaut mesuré (+38,7 points d'équité surestimée à la
   river) est exactement celui que le CFR corrige : raisonner sur des ensembles
   d'information et des ranges conditionnées par l'historique, pas sur une main uniforme.
2. **Petit jeu exact avant Hold'em.** Regret matching, stratégie moyenne et best-response
   sur Kuhn puis Leduc, avec exploitabilité calculée exactement, avant toute abstraction
   heads-up de Hold'em à mises limitées.
3. **PokerKit reste l'arbitre.** Séparer l'état complet de l'arbitre de l'observation de
   l'agent, et tester chaque correspondance entre abstraction et action légale réelle.
4. **Banc d'évaluation existant réutilisé.** Mêmes protocoles (alternance des positions,
   graines séparées et disjointes entre entraînement et test, IC sur blocs) contre une
   population : Random, Heuristic, Equity et TAG. Viser d'abord de battre nettement le TAG.
5. **Rake traité à part.** Le CFR standard suppose un jeu à deux joueurs et à somme nulle ;
   avec rake, le jeu n'est plus à somme nulle. Entraîner sans rake, puis mesurer l'impact du
   rake à l'évaluation, comme ici.
6. **Budget de calcul.** Le coût par décision devient un critère : la mesure ci-dessus montre
   qu'un calcul plus long n'est utile que si le modèle sous-jacent est juste.

Aucun entraînement CFR/self-play, aucune connexion Jev et aucun site tiers n'a été utilisé
dans cette mission.

## Mission 2 : Equity contre Random — 20 plus gros pots gagnés et perdus

Pots disputés et profits nets en BB. Les identifiants renvoient aux traces privées ; aucune carte cachée n’est publiée ici. Les égalités de taille sont départagées selon le tri fixé dans l’audit.

| Main gagnée | Pot | Net Equity | Main perdue | Pot | Net Equity |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 400.00 | +197.00 | 7 | 400.00 | -200.00 |
| 5 | 400.00 | +197.00 | 49 | 400.00 | -200.00 |
| 8 | 400.00 | +197.00 | 58 | 400.00 | -200.00 |
| 10 | 400.00 | +197.00 | 81 | 400.00 | -200.00 |
| 12 | 400.00 | +197.00 | 87 | 400.00 | -200.00 |
| 22 | 400.00 | +197.00 | 123 | 400.00 | -200.00 |
| 35 | 400.00 | +197.00 | 138 | 400.00 | -200.00 |
| 43 | 400.00 | +197.00 | 167 | 400.00 | -200.00 |
| 57 | 400.00 | +197.00 | 196 | 400.00 | -200.00 |
| 65 | 400.00 | +197.00 | 202 | 400.00 | -200.00 |
| 67 | 400.00 | +197.00 | 210 | 400.00 | -200.00 |
| 78 | 400.00 | +197.00 | 238 | 400.00 | -200.00 |
| 79 | 400.00 | +197.00 | 239 | 400.00 | -200.00 |
| 90 | 400.00 | +197.00 | 242 | 400.00 | -200.00 |
| 99 | 400.00 | +197.00 | 254 | 400.00 | -200.00 |
| 104 | 400.00 | +197.00 | 257 | 400.00 | -200.00 |
| 109 | 400.00 | +197.00 | 310 | 400.00 | -200.00 |
| 118 | 400.00 | +197.00 | 325 | 400.00 | -200.00 |
| 134 | 400.00 | +197.00 | 328 | 400.00 | -200.00 |
| 147 | 400.00 | +197.00 | 354 | 400.00 | -200.00 |

## Mission 3 : Equity contre TAG, graine 31001 — 20 plus gros pots gagnés et perdus

Pots disputés et profits nets en BB. Les identifiants renvoient aux traces privées ; aucune carte cachée n’est publiée ici. Les égalités de taille sont départagées selon le tri fixé dans l’audit.

| Main gagnée | Pot | Net Equity | Main perdue | Pot | Net Equity |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 5929 | 384.00 | +189.00 | 342 | 400.00 | -200.00 |
| 8445 | 384.00 | +189.00 | 1034 | 400.00 | -200.00 |
| 1030 | 345.00 | +169.50 | 2184 | 400.00 | -200.00 |
| 2062 | 345.00 | +169.50 | 6686 | 400.00 | -200.00 |
| 1206 | 322.00 | +158.00 | 8137 | 400.00 | -200.00 |
| 1748 | 322.00 | +158.00 | 9956 | 400.00 | -200.00 |
| 8962 | 322.00 | +158.00 | 273 | 384.00 | -192.00 |
| 207 | 288.00 | +141.00 | 1541 | 384.00 | -192.00 |
| 889 | 288.00 | +141.00 | 2979 | 384.00 | -192.00 |
| 1685 | 288.00 | +141.00 | 2983 | 384.00 | -192.00 |
| 1879 | 288.00 | +141.00 | 3289 | 384.00 | -192.00 |
| 1901 | 288.00 | +141.00 | 4465 | 384.00 | -192.00 |
| 2797 | 288.00 | +141.00 | 5777 | 384.00 | -192.00 |
| 5953 | 288.00 | +141.00 | 6261 | 384.00 | -192.00 |
| 8193 | 288.00 | +141.00 | 6895 | 384.00 | -192.00 |
| 9017 | 288.00 | +141.00 | 7431 | 384.00 | -192.00 |
| 9093 | 288.00 | +141.00 | 8103 | 384.00 | -192.00 |
| 9399 | 288.00 | +141.00 | 8231 | 384.00 | -192.00 |
| 9437 | 288.00 | +141.00 | 8269 | 384.00 | -192.00 |
| 9627 | 288.00 | +141.00 | 9139 | 384.00 | -192.00 |

Le rejeu supplémentaire Equity/TAG (31001) a contrôlé **10 000 mains et 50 709 décisions**, puis reproduit les politiques sur les 40 mains sélectionnées. Les classements des 40 showdowns sont confirmés par Treys. Aucune divergence d’observation, carte cachée ou profit n’est détectée.

Sur cette graine, 6 mains comportent un all-in, toutes perdantes pour Equity : −1 200 BB. Les autres mains totalisent −17 237,22 BB nets. La perte ne se résume donc pas à quelques all-in.

Dans les 20 plus gros pots perdus contre TAG, la dernière décision Equity est river ; une estimation uniforme refaite à 1024 tirages donne en moyenne 83,0 % d’équité, alors que la main effectivement détenue par le TAG gagne. Ce constat est **sélectionné sur les pertes** et ne mesure donc pas à lui seul un biais global. Les 20 plus gros pots gagnés donnent 92,5 % d’équité uniforme moyenne. Ces vérifications post-mortem utilisent les cartes réelles uniquement dans l’auditeur hors ligne, jamais dans l’agent.
