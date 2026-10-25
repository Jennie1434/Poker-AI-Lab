# Mission 4 — première IA de poker entraînable (CFR / self-play)

Documents relus avant les changements : `MISSION_3.md`, `MISSION_3_ETAT.md`,
`BENCHMARK_LAB.md`, `AUDIT_POKER_AI_LAB.md`. Le projet existant est réutilisé :
interface `Agent.choose_action(observation)`, pont serveur `play_action`,
benchmark `pokerbench.benchmark`, rake et statistiques de la mission 3. PokerKit
reste l'unique autorité sur les cartes, les actions légales et les gains.

> **Rapport en cours de rédaction** : entraînement Hold'em et benchmark en cours d'exécution. Les sections Kuhn, Leduc et abstraction sont définitives.

## Ordre de livraison

Les étapes ont été validées et poussées séparément, dans l'ordre demandé :

| Commit | Contenu | Validation |
| --- | --- | --- |
| `9eb2872` | CFR, CFR+ et MCCFR ; Kuhn et Leduc ; best response exacte ; checkpoints | 16 tests, 659 tests Python au total |
| `f7cb985` | Abstraction Hold'em, `CFRAgent`, entraînement, **protocole d'évaluation figé** | 668 tests Python au total |
| (ce rapport) | Entraînement, benchmark, analyse et rapport | voir « Tests exécutés » |

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

<!-- résultats Hold'em à venir -->
