# Mission 2 — benchmark reproductible Poker AI Lab

## Protocole

Le moteur `Hand`/PokerKit 0.7.6 est inchangé. Le nouveau module
`pokerbench.benchmark` orchestre des mains heads-up cash à jetons fictifs,
blinds 50/100, sans ante, avec 20 000 jetons (200 BB) par joueur au début de
**chaque** main. Les tailles de mise sont celles proposées par le moteur :
ce n'est pas une exploration de toutes les tailles possibles en no-limit.

Une expérience publiée par la CLI doit contenir au moins 10 000 mains et un
nombre pair de mains. Le bouton alterne strictement : 5 000 BTN/SB et 5 000 BB
par agent sur 10 000 mains. Les mains sont indépendantes, **non dupliquées**.
Le nombre demandé et le nombre réellement terminé sont conservés ; un échec
rend l'expérience `failed`, sans remplacement silencieux des mains ni affichage
comme résultat complet. Un dossier existant n'est jamais écrasé.

Chaque graine de main est obtenue par SHA-256 de
`v1:{master}:{domain}:{hand_index}`, avec les 128 premiers bits interprétés en
entier. La distribution utilise le master `deck_seed` et le domaine `deck` ;
les politiques utilisent `policy_seed` et `policy:a` / `policy:b`. Les RNG sont
réinitialisés par main : le nombre de décisions d'une main ne décale pas le
paquet ou la politique de la suivante. Les graines de distribution ne sont
jamais transmises aux agents. Python et les bibliothèques doivent conserver
leurs versions pour reproduire les fichiers à l'identique.

## Agents comparés

- **RandomAgent** : uniforme sur les identifiants d'actions proposés, et non sur
  toutes les tailles de mises possibles.
- **HeuristicAgent** : check, call jusqu'à un tiers du pot, sinon fold ; ne
  relance jamais et ignore ses cartes. C'est volontairement une référence faible.
- **EquityHeuristicAgent** : estime l'équité heads-up avec 64 tirages Monte Carlo
  par décision contre une main uniforme parmi les cartes inconnues. Utilise
  uniquement les deux cartes propres et le board public ; départage les égalités
  par une demi-victoire. Relance du minimum proposé si équité >= 65 % et relance
  non all-in disponible, sinon check gratuit, call si
  `équité >= coût_call / (pot + coût_call) + 0,02`, sinon fold. Treys sert à
  estimer l'équité ; **PokerKit reste seul responsable du règlement réel**.

L'agent amélioré ne modélise ni ranges conditionnées par les actions adverses,
ni fold equity, ni implied odds, ni mises futures. Une estimation à 64 tirages
est bruitée. Il n'est ni optimal ni entraîné, et le benchmark ne démontre pas
qu'il serait meilleur face à tous les adversaires.

## Statistiques

`bb/100 = 100 * somme(profits_jetons) / (100 * nombre_mains)`.
Les profits totaux sont également exportés en jetons et en BB. Le « win rate »
est la fraction de mains avec profit **strictement positif** ; les pertes et
mains à zéro sont séparées. Ce n'est ni le taux de showdowns gagnés ni une
estimation d'équité. Les métriques existent pour les résultats bruts et nets.

Chaque bloc contient deux mains successives, une à chaque position. L'IC à
95 % est `moyenne_blocs ± 1,95996398454 * écart_type_blocs / sqrt(nombre_blocs)`,
converti en bb/100. On utilise les moyennes de 5 000 blocs indépendants,
**jamais les décisions comme échantillons indépendants**. C'est un intervalle
normal asymptotique, pas une garantie exacte à taille finie. L'API Python
accepte de petites tailles pour les tests mais les marque `small_sample` ;
la CLI refuse moins de 10 000 mains.

Les gros pots donnent des distributions très dispersées ; un seul ensemble de
10 000 mains reste limité. Les deux expériences utilisent les mêmes graines de
paquet : elles sont corrélées entre elles. Les IC décrivent chaque matchup
séparément, pas la différence entre agents de deux expériences. Aucun test de
supériorité entre tous les agents, correction de comparaisons multiples ou
mesure d'exploitabilité n'est revendiqué. Pour comparer formellement deux
politiques face au même adversaire, analyser les différences appariées sur les
mêmes blocs puis multiplier les graines maîtresses indépendantes.

## Rake

Paramètres CLI : `--rake-percent`, `--rake-cap-bb`, et
`--no-flop-no-drop` / `--no-no-flop-no-drop` (syntaxe BooleanOptionalAction).
Le scénario exécuté utilise **5 %, plafond 3 BB par main, no-flop-no-drop**.
Le cas sans rake correspond aux résultats bruts ; `--rake-percent 0` permet
également une expérience à taux zéro.

En heads-up, les contributions effectivement disputées sont
`2 * min(contributions_cumulées)` ; toute mise excédentaire non suivie est
rendue et exclue. Le prélèvement est le minimum du pourcentage de ce pot et du
plafond, arrondi vers le bas au jeton entier. Il est nul sans flop si l'option
est active. Il est réparti proportionnellement aux gains du pot, avec méthode
des plus grands restes et priorité à l'ordre des sièges en cas d'égalité.
Ainsi, les pots partagés sont traités explicitement. L'unité de comptabilité du
rake est 1 jeton, distincte du pas de mise de 50 jetons.

À chaque règlement : somme des profits bruts = 0 ; somme des profits nets =
−rake. Le rake est calculé **main par main après le règlement PokerKit**, pas
par soustraction d'une moyenne globale. C'est un scénario comptable sur les
mêmes décisions et les mêmes donnes. Les politiques ne s'adaptent pas au rake,
et les stacks sont réinitialisés à la main suivante : ces résultats ne simulent
pas une session persistante, un casino particulier, ni un équilibre stratégique
avec prélèvement. Aucun changement du moteur ou de son règlement n'a été fait.

## Exports et confidentialité

Chaque dossier privé d'expérience (mode 0700) contient :

- `experiment.json` : statut, paramètres, règles, métriques et IC, version Python,
  versions PokerKit/Treys, commit, indicateur d'arbre modifié et SHA-256 des
  sources effectives et des exports. Le commit seul ne suffit pas car ce travail
  est non commité.
- `hands.csv` : une ligne par main terminée, bouton, bloc, décisions, flop,
  pot disputé, rake et profits bruts/nets de chaque siège.
- `decisions.jsonl` : historique local de chaque observation autorisée et action.
  Les observations ne contiennent ni graine ni paquet ni cartes cachées adverses.
  Les mains propres successives des différents acteurs rendent **l'ensemble du
  journal privé** : ne pas le servir à un agent ou une salle. Les graines du
  manifeste permettent aussi de reconstruire les donnes ; elles sont réservées
  à cette expérience hors ligne, pas à des parties privées en cours.

Ces sorties sont sous `artifacts/`, ignoré par Git. Le tableau de bord n'inclut
que paramètres et statistiques agrégées, jamais les journaux de décisions ou
les cartes. Il s'agit d'une page autonome hors ligne, distincte des salles web
et des classements publics de JevPokerBench. Aucune route publique n'est ajoutée.

## Commandes de reproduction

Depuis `/workspace/Poker-AI-Lab`, dans un nouvel emplacement de sortie :

```bash
.venv/bin/python -m pokerbench.benchmark --hands 10000 \
  --deck-seed 1234 --policy-seed 5678 \
  --rake-percent 5 --rake-cap-bb 3 --no-flop-no-drop \
  --output artifacts/reproduction/random-v-heuristic

.venv/bin/python -m pokerbench.benchmark --hands 10000 --agent-b equity \
  --equity-samples 64 --deck-seed 1234 --policy-seed 5678 \
  --rake-percent 5 --rake-cap-bb 3 --no-flop-no-drop \
  --output artifacts/reproduction/random-v-equity

.venv/bin/python -m pokerbench.benchmark_dashboard \
  artifacts/reproduction/random-v-heuristic/experiment.json \
  artifacts/reproduction/random-v-equity/experiment.json \
  --output artifacts/reproduction/dashboard.html
```

Ouvrir le HTML dans un navigateur ou le servir localement avec
`python3 -m http.server 8098 --bind 127.0.0.1 --directory artifacts/reproduction`.
Ce serveur est réservé à votre poste local : ne pas exposer les journaux privés.
Le tableau permet de filtrer l'expérience, de basculer brut/net et de comparer
les bb/100 avec leurs intervalles, profits et taux de mains gagnantes.

## Validation exécutée

```bash
.venv/bin/python -m pytest -q backend/tests/test_benchmark.py backend/tests/test_agents.py
.venv/bin/python -m pytest -q
# Dans frontend :
npm test
npm run build
PB_BASE_URL=http://127.0.0.1:8097 PB_BROWSER_EXECUTABLE=/usr/bin/chromium npm run test:browser
PB_BENCHMARK_DASHBOARD=/workspace/Poker-AI-Lab/artifacts/mission2/dashboard.html \
  node tests/benchmark-dashboard.mjs
```

Résultats : 35 tests ciblés réussis ; **624 tests Python réussis** (22 nouveaux
pour cette mission), **26 tests frontend réussis**, compilation TypeScript/Vite
réussie, smoke navigateur de l'application réussi. Le navigateur géré interdit
la navigation `file://` ; le test du tableau charge donc le HTML via
`page.setContent`, sans désactiver la politique du navigateur et sans connexion
externe. Les sélecteurs brut/net, filtre d'expérience, graphiques et affichages
desktop/mobile sont contrôlés.

L'expérience RandomAgent/HeuristicAgent a été exécutée une seconde fois :
`experiment.json`, `hands.csv` et `decisions.jsonl` sont identiques octet par octet.
SHA-256 de son `hands.csv` :
`c00af91b061db550219a22bb7a13e4a1e41a1c4355f8adcf0d3838c1b1951cb3`.
La répétition n'ajoute pas 10 000 observations indépendantes à l'analyse.

## Prochaines étapes

Valider ce protocole, puis étendre aux graines indépendantes et au matchup
heuristique simple contre équité ; comparer les améliorations par différences
appariées et fixer un budget de mains à l'avance. Ajouter une analyse de
sensibilité au nombre de tirages d'équité et aux scénarios de rake, puis une
politique explicitement consciente du rake. Garder le CFR et les connexions
Jev hors de ce jalon. Aucun entraînement ni connexion fournisseur n'a été lancé,
et aucune automatisation de plateforme de poker tierce n'est incluse.

## Résultats observés — 25 octobre 2026

20 000 mains originales terminées (deux expériences de 10 000), plus une répétition identique de 10 000 mains pour vérifier la reproductibilité. Chaque agent a exactement 5 000 mains au bouton et 5 000 à la big blind par expérience.

| Expérience | Agent | Profit brut (BB) | Profit net (BB) | bb/100 brut [IC 95 %] | bb/100 net [IC 95 %] | Mains gagnantes nettes |
| --- | --- | ---: | ---: | --- | --- | ---: |
| random-v-heuristic | random | 11447.50 | 10822.90 | 114.47 [111.84 ; 117.11] | 108.23 [105.78 ; 110.67] | 91.76 % |
| random-v-heuristic | heuristic | -11447.50 | -11516.20 | -114.47 [-117.11 ; -111.84] | -115.16 [-117.72 ; -112.60] | 8.07 % |
| random-v-equity | random | -229226.00 | -234159.70 | -2292.26 [-2486.60 ; -2097.92] | -2341.60 [-2534.72 ; -2148.48] | 57.73 % |
| random-v-equity | equity | 229226.00 | 220962.80 | 2292.26 [2097.92 ; 2486.60] | 2209.63 [2017.27 ; 2401.98] | 40.86 % |

Rake cumulé : **693,30 BB** (aléatoire/simple) et **13 196,90 BB** (aléatoire/équité).

Les profits très élevés de l’agent à équité concernent uniquement ce RandomAgent, qui peut engager des sommes importantes avec une main faible. Son taux de mains gagnantes ne décrit donc pas à lui seul sa rentabilité. Aucun résultat contre des joueurs humains ou une politique compétitive n’est établi.

Les deux exports ont été revalidés indépendamment depuis les CSV : 10 000 identifiants successifs, positions exactes, profits, bb/100, conservation et checksums des fichiers.

Sorties locales : `artifacts/mission2/random-v-heuristic/`, `artifacts/mission2/random-v-equity/` et `artifacts/mission2/dashboard.html`. Les 10 000 mains de la répétition sont dans `artifacts/mission2/repeat-random-v-heuristic/`.
