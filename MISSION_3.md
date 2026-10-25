# Mission 3 — évaluation de la force des agents

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

## Faiblesses structurelles à confronter aux résultats

1. **Ranges** : l'équité d'EquityHeuristicAgent suppose une main adverse uniforme
   même après plusieurs relances. Augmenter les tirages réduit le bruit, pas ce
   biais. Une main forte contre une range uniforme peut être dominée par une
   range de value très serrée.
2. **Préflop** : pas de table d'ouverture ni de défense par position, pas de
   logique de 3-bet/4-bet et pas de traitement particulier des mains spéculatives
   profondes. Les choix dépendent de seuils d'équité uniforme.
3. **Relances** : relance minimale dès 65 % d'équité estimée, même après une
   escalade adverse ; pas de calcul de fold equity, pas de tailles différenciées
   pour value/protection/bluff, pas de limite de relances par street.
4. **Postflop et risque** : le seuil du call utilise les pot odds et une marge
   fixe de 2 points, sans réalisation d'équité, mises futures, reverse implied
   odds, stack-to-pot ratio ou risque de stack entier.
5. **Bluffs** : aucune politique de bluff ou semi-bluff délibérée, ni fréquences
   équilibrées, ni sélection de bloqueurs. Le bruit Monte Carlo n'est pas une
   stratégie de bluff.
6. **Blindes** : la position ne modifie pas la politique d'Equity ; les décisions
   de défense doivent être analysées séparément des vols faciles contre un TAG
   qui n'ouvre que 22,8 % des combinaisons.

Les fréquences observées et les résultats ne permettent pas d'attribuer
causalement un écart à une seule règle. Pour cela, il faudra des ablations
préenregistrées (range, sizing, seuil de call, position), sur les mêmes graines.

## Reproduction

Depuis `/workspace/Poker-AI-Lab`, choisir des sorties inexistantes ; aucune
expérience antérieure n'est écrasée :

```bash
# Rejouer l'audit des anciennes mains ; créer le dossier parent auparavant.
mkdir -p artifacts/mission3-reproduction-audit
.venv/bin/python -m pokerbench.mission3 audit artifacts/mission2/random-v-equity \
  --output artifacts/mission3-reproduction-audit/equity.json
.venv/bin/python -m pokerbench.mission3 audit artifacts/mission2/random-v-heuristic \
  --output artifacts/mission3-reproduction-audit/simple.json

# Plan complet : 90 000 mains principales + 2 000 mains de sensibilité.
.venv/bin/python -m pokerbench.mission3 run --workers 3 \
  --output artifacts/mission3-reproduction
.venv/bin/python -m pokerbench.mission3 analyze artifacts/mission3-reproduction \
  --output artifacts/mission3-reproduction/analysis.json

# Diagnostic de coût sur états fixes.
.venv/bin/python -m pokerbench.mission3 cost artifacts/mission2/random-v-equity \
  --output artifacts/mission3-reproduction-audit/cost.json

# Exemple d'une confrontation individuelle.
.venv/bin/python -m pokerbench.benchmark --hands 10000 \
  --agent-a equity --agent-b tag --deck-seed 31001 --policy-seed 41001 \
  --equity-samples 64 --tag-samples 64 --measure-time \
  --output artifacts/mission3-single
```

Le temps CPU et le temps mural varient d'une exécution à l'autre ; les actions,
profits et observations restent reproductibles aux mêmes sources, versions et
graines. Les nouveaux fichiers de manifeste contiennent les écarts-types et
la configuration TAG ; les anciens manifests de mission 2 sont conservés.
Les empreintes des sources et des données sont enregistrées par expérience.

## Tests et priorités CFR/self-play

Commandes exécutées :

```bash
.venv/bin/python -m pytest -q backend/tests/test_mission3.py backend/tests/test_benchmark.py backend/tests/test_agents.py
.venv/bin/python -m pytest -q
# Depuis frontend :
npm test
npm run build
PB_BASE_URL=http://127.0.0.1:8097 PB_BROWSER_EXECUTABLE=/usr/bin/chromium npm run test:browser
```

**52 tests ciblés et 641 tests Python réussis** ; 17 nouveaux cas pour cette
mission. Couverture ajoutée : classes préflop, défense BB, rejet des all-in
spéculatifs, seuils de risque postflop, tirages, confidentialité et
reproductibilité, audit détectant une observation falsifiée même si son checksum
est recalculé, rake indépendant monotone, tailles/graines du plan et unités des
écarts-types. Les **26 tests frontend et la compilation** passent également.
Les vérifications numériques des fichiers complets sont distinctes de ces tests.

Priorités après cette évaluation, sans lancer d'entraînement dans cette mission :

1. Définir un jeu abstrait heads-up à mises limitées et ensembles d'information
   à rappel parfait ; tester regret matching, stratégie moyenne et best-response
   sur Kuhn/Leduc avant toute revendication sur Hold'em.
2. Conserver PokerKit comme arbitre des transitions réelles ; séparer état complet
   d'arbitre et observation d'agent, et vérifier chaque mapping d'abstraction.
3. Benchmarker une population d'adversaires diversifiée, geler checkpoints et
   budgets d'évaluation, utiliser des graines d'entraînement et de test disjointes.
4. Ajouter des tests d'exploitabilité dans le petit jeu, des ablations de ranges
   et de sizing, et une évaluation multi-graines des politiques moyennes.
5. Traiter le rake séparément : le cadre à deux joueurs et somme nulle du CFR
   standard ne s'étend pas automatiquement au jeu à prélèvement variable.

Aucun entraînement CFR/self-play, connexion Jev ou site tiers n'a été lancé.

## Mission 2 : Equity contre Random — 20 plus gros pots gagnés et perdus

Pots disputés et profits nets en BB. Les identifiants renvoient aux traces locales ; aucune carte cachée n’est publiée ici. Les égalités de taille sont départagées selon le tri fixé dans l’audit.

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

Pots disputés et profits nets en BB. Les identifiants renvoient aux traces locales ; aucune carte cachée n’est publiée ici. Les égalités de taille sont départagées selon le tri fixé dans l’audit.

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
