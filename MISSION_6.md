# Mission 6 — corriger le jeu trop défensif de CFR V2

Repris depuis `main` (Missions 1 à 5). PokerKit reste l'unique autorité sur les cartes, les
actions légales et les gains. **V1 et V2 sont conservées intégralement** : leurs fichiers de
politique ne sont pas modifiés, et leurs décisions enregistrées lors des Missions 4 et 5 se
rejouent à l'identique avec le code de cette mission. Aucune intégration à un site tiers.

## Synthèse

| Demande | Résultat |
| --- | --- |
| Audit des 49 mains | **Données non accessibles ici** (base locale de votre ordinateur) ; outil d'audit en lecture seule prêt, avec la procédure d'export. Rien n'a été inventé. |
| Comptabilité et bb/100 | **Pas d'erreur** : classement, gains PokerKit et panneau concordent (9 parties testées, dont une à 0 / 0 exact). Ajout des gains et pertes bruts et d'un test de non-régression. |
| HyperAggressiveAgent | VPIP 92,6 %, PFR 85,3 % (cible 92 / 88). |
| V2 contre profils agressifs | V2 **bat largement** l'hyper-agressif (+376,9 puis +386,5 bb/100) en ne gagnant que 18 % des mains. Contre TAG, V2 300k fait **+9,8 [+1,7 ; +17,9]** sur 120 000 mains regroupées (a posteriori). |
| Causes de la passivité | **Politique apprise**, pas les replis : la grosse blinde abandonne la moitié la plus faible de ses mains face à 3 BB ; nombreux abandons à la river. S'y ajoutent 10 % de replis hors arbre contre l'hyper-agressif. |
| Stratégie améliorée | **Couche d'adaptation fondée sur les statistiques publiques** : **+131,3 bb/100 [+59,8 ; +202,8]** contre l'hyper-agressif, **jeu identique main pour main** contre TAG, calling station et Equity. |
| CFR V3 | Entraînée (2 graines × 300 000 itérations, environ 3 h CPU chacune). **Moins bonne que V2** contre l'hyper-agressif (−254) et Equity (−83), meilleure contre la calling station (+76), non concluante contre TAG. Probablement sous-entraînée. |
| Intégration | **CFR V2 · adaptive** (adversaire par défaut) et **CFR V3 · 300k (experimental)** ajoutées aux salles et au Spectate après les tests fonctionnels ; V1 et V2 conservées. |

Ces résultats sont des simulations contre des bots de test ; ils ne garantissent aucun gain
contre des humains.

## 1. Les 49 mains observées : accès et audit

**Les 49 mains ne sont pas accessibles dans l'environnement de développement.** Elles se
trouvent dans la base SQLite de l'ordinateur où la partie a été jouée. Seules des bases de tests
synthétiques existent ici. Aucun chiffre de cette partie n'a été inventé, et les observations
transmises (humain VPIP 92 % / PFR 88 % / 90 % de mains gagnées ; V2 VPIP 55 % / PFR 29 % /
10 % de mains gagnées) servent uniquement de cible de calibration.

Pour auditer la vraie partie, il faut exporter son historique, ce que seul le propriétaire peut
faire. L'export ne contient aucune carte adverse non montrée :

```bash
# application lancée, compte connecté ; <id> figure dans l'adresse de la table (#rooms/<id>)
# ouvrir dans le navigateur et enregistrer le JSON :
http://127.0.0.1:8097/api/rooms/<id>/history?limit=200
# puis, en lecture seule :
.venv/bin/python -m pokerbench.room_audit history.json --output audit.json
```

`backend/pokerbench/room_audit.py` mesure, par joueur :
- les décisions et les folds face aux mises, par street, ainsi que la défense de la grosse blinde
  face à une ouverture ;
- le VPIP, le PFR, le gain net et le bb/100 ;
- la répartition des tailles de pot ;
- les relances postflop. Un bluff n'est compté que si les cartes ont été révélées à l'abattage ;
  les autres mains sont comptées à part.

L'outil ne modifie aucun résultat, ce que vérifie un test.

## 2. Comptabilité des salles et bb/100

**Aucune erreur de comptabilité trouvée.** Trois calculs indépendants ont été comparés sur 9
parties simulées de 49 mains, entre un humain très agressif (relance dans 85 % des cas) et
CFR V2 :

1. le classement de la salle : `tapis + réserve − capital initial` ;
2. la somme des gains PokerKit de chaque main ;
3. le panneau « Hand history and statistics ».

Ils concordent dans tous les cas, malgré les remises à zéro à 400 BB. Une partie a même fini à
**exactement 0 / 0**, avec des pots de plusieurs centaines de BB gagnés puis perdus. Un net nul
peut donc être réel. Le bb/100 est `100 × gain net en BB / mains jouées`.

Une confusion apparente est venue de la réserve : après une remise à zéro, le tapis gagné passe
dans la réserve, et un joueur peut afficher un tapis inférieur à 200 BB avec un profit positif.

Changements :
- **test de non-régression** (`test_aggressive_session_ledgers_agree_across_cash_resets`) : les
  trois calculs doivent rester égaux sur 49 mains agressives avec remises à zéro ;
- le panneau affiche désormais aussi les **gains bruts / pertes brutes** et la **plus grosse
  main**, pour qu'un « 0 » se lise comme « +X / −X ».

**Taille d'échantillon** : contre un joueur hyper-agressif, l'écart-type mesuré est de
**53,6 BB par main**. Sur 49 mains, l'IC à 95 % du bb/100 vaut donc environ **±1 500 bb/100** :
ni le net de 0, ni les 10 % de mains gagnées ne permettent de juger la force de l'IA.

## 3. Adversaires de test

`backend/pokerbench/agents.py` :

- **HyperAggressiveAgent**, calibré sur le joueur observé : relance presque toutes les mains
  préflop avec des tailles variées, mise la plupart des flops quand on lui checke, continue à
  miser avec des mains faibles à fréquence fixe et ne se couche qu'avec une main faible face à une
  grosse mise. Mesuré contre un adversaire qui agit à chaque main : **VPIP 92,6 %, PFR 85,3 %**
  (cible : 92 / 88).
- **CallingStationAgent** : paie presque tout et ne relance presque jamais (PFR 0 %).

Tous deux lisent uniquement leur observation filtrée, et un test vérifie qu'ils ignorent les
cartes cachées. Ils sont aussi disponibles dans le mode Spectate.

## 4. Mesure de référence : V2 contre quatre profils

Protocole fixé avant l'exécution (`mission6.py`, commit `cf0b6c7`) : V2 300k contre hyper, TAG,
calling station et equity, sur 3 graines neuves (101001–101003 / 111001–111003), 10 000 mains par
graine, bouton alterné, rake 5 % plafonné à 3 BB.

| V2 contre… | bb/100 net [IC 95 %] | 0 % de rake | Graines | Bouton / BB | Mains gagnées | Sorties d'arbre | Verdict |
| --- | ---: | ---: | --- | --- | ---: | ---: | --- |
| **HyperAggressive** | **+376,9 [+316,2 ; +437,7]** | +409,8 | +409,6 / +345,9 / +375,3 | +526,6 / +227,3 | **18 %** | **10,6 %** | bat |
| TightAggressive | +0,8 [−14,5 ; +16,2] | +7,4 | +1,8 / −6,3 / +7,0 | −7,2 / +8,9 | 76 % | 0,0 % | non concluant |
| CallingStation | +98,6 [+63,4 ; +133,9] | +139,5 | +91,4 / +109,3 / +95,1 | +121,3 / +75,9 | 47 % | 0,9 % | bat |
| EquityHeuristic | +116,1 [+78,8 ; +153,5] | +144,8 | +113,7 / +120,4 / +114,3 | +85,4 / +146,9 | 49 % | 3,6 % | bat |

**V2 bat largement le profil hyper-agressif, tout en ne gagnant que 18 % des mains**, ce qui
reproduit la répartition observée contre l'humain. Être « défensif » ne veut pas dire perdre : V2
abandonne beaucoup de petits pots et gagne les gros. L'humain réel peut toutefois jouer mieux que
cet agent de test, par exemple en se couchant face à la force ou en bluffant de façon adaptée.

Fréquences de V2 (moyenne des 3 graines) :

| V2 contre… | VPIP | PFR | Fold de la BB face à une relance | Fold face à une mise à la river | Relances au flop |
| --- | ---: | ---: | ---: | ---: | ---: |
| HyperAggressive | 66 % | 43 % | **52 %** | 45 % | 23 % |
| TAG | 77 % | 51 % | 60 % | 51 % | 46 % |
| CallingStation | 59 % | 44 % | — | 46 % | 49 % |
| Equity | 61 % | 44 % | 33 % | 45 % | 42 % |

## 5. Causes de la passivité

Lecture directe de la stratégie moyenne apprise par V2 (probabilités par situation et par groupe
de force de main, 0 = le plus faible) :

| Situation | Comportement appris |
| --- | --- |
| Grosse blinde face à une ouverture à 3 BB | **se couche 98 à 100 % du temps avec les groupes 0 à 3** (la moitié des mains), 57 % avec le groupe 4 |
| Grosse blinde face à une ouverture à 2 BB | se couche surtout avec les groupes 0 (93 %) et 1 (63 %), paie largement le reste |
| River face à une mise | se couche 68 à 94 % du temps avec les groupes 0 à 4 (jusqu'à une paire moyenne) |
| Face à une deuxième relance, toutes streets | se couche environ 55 % du temps |
| River, quand on lui checke | **bluffe** : 66 % de mises avec le groupe le plus faible, dont 22 % d'all-in |
| Flop avec tirage, quand on lui checke | mise 84 % du temps (groupe 1), avec des semi-bluffs déjà présents |

Conclusions :

1. **La politique apprise, pas la règle de repli, explique l'essentiel.** Ces abandons sont une
   réponse « d'équilibre » dans l'abstraction V2, face à un adversaire équilibré. Dans un jeu
   postflop grossier (8 groupes préflop, aucune mémoire de sa propre force préflop), une main
   moyenne défendue en grosse blinde ne parvient pas à réaliser son équité ; se coucher y paraît
   donc « correct ».
2. **Les replis hors abstraction comptent contre l'hyper-agressif** : 10,6 % des décisions, contre
   0 % face à TAG, à cause des guerres de relances au-delà de 3 relances par street.
3. **La rareté des bluffs perçue est surtout un effet de l'adversaire.** V2 bluffe quand on lui
   checke, mais un joueur qui mise à chaque street ne lui en laisse presque jamais l'occasion.
4. Contre un adversaire hyper-agressif, ces abandons coûtent de l'argent : sa range est presque
   aléatoire, si bien qu'une main moyenne a l'équité nécessaire pour payer.

## 6. Stratégie améliorée

### Couche d'adaptation fondée sur les statistiques publiques (`adaptive.py`)

`AdaptiveCFRAgent` superpose des règles explicites à une politique CFR gelée, **à partir des seules
statistiques publiques** que les salles transmettent déjà aux agents (VPIP, PFR, 3-bet). Il
n'utilise jamais les cartes cachées.

- Le PFR adverse est rapproché d'un PFR présumé de 25 %, pondéré comme 20 mains : quelques mains
  ne suffisent pas à déclencher l'adaptation. Celle-ci s'active progressivement au-delà de 40 %
  et atteint son plein effet à 75 %.
- **Défense** : face à une mise, préflop comme postflop, une partie de la probabilité de se coucher
  passe sur le call si l'équité contre une main aléatoire dépasse la cote du pot de 3 points. Face
  à un joueur qui relance presque tout, une main aléatoire est un bon modèle de sa range.
- **Valeur** : avec une équité ≥ 75 %, la moitié de la probabilité de payer passe sur une relance.
- **Bluffs cohérents** : avec une équité < 35 % et sans mise à payer, la probabilité de miser est
  divisée par deux. Bluffer un joueur qui ne se couche presque jamais n'est pas justifié. Les
  semi-bluffs et bluffs appris par CFR restent intacts contre les autres profils.
- Sous le seuil, la politique de base est jouée **sans aucune modification**.

Le benchmark peut exposer les mêmes statistiques publiques que les salles (option `public_stats`,
désactivée par défaut, donc sans effet sur les expériences antérieures). Le mode Spectate les
transmet aussi.

Pilote exploratoire (graines dédiées 151001 / 161001, 4 000 mains, hors évaluation finale) :
- **contre HyperAggressive** : différence appariée V2+adaptation − V2 de **+299,3 bb/100
  [+104,1 ; +494,5]** ; le fold de la grosse blinde face aux relances passe de 51 % à 11 % ;
- **contre TAG** : jeu **identique main pour main** (différence de 0,0), car le PFR public de TAG
  reste sous le seuil.

### Abstraction V3 (`holdem_v3.py`)

| Dimension | V2 | V3 |
| --- | --- | --- |
| Groupes préflop | 8 | **10** |
| Groupes flop / turn | 6 × tirage = 12 | **8 × tirage = 16** |
| Groupes river | 8 | **10** |
| Mémoire | groupe courant seulement | **+ niveau de force préflop (3 niveaux)** dans les clés postflop |
| Relance face à une mise | pot | **½ pot ou pot** |
| Relances par street | 3 | **4** |

V3 est vérifiée comme V2 : 250 mains jouées en parallèle dans PokerKit et dans l'arbre abstrait,
après un vrai export et rechargement de la politique. Le test contrôle les jetons engagés,
l'historique reconstruit, les actions légales et la clé à chaque décision.

## 7. Coût et entraînement de V3

| | V2 | V3 |
| --- | ---: | ---: |
| Coût par itération (mesuré, CPU libres) | 21,4 ms | **28,2 ms** |
| Ensembles d'information à 10 000 itérations | 9 685 | **55 764** |
| Mémoire du processus | 44 Mo | **71 Mo** |

Ressources disponibles : 4 CPU, 15 Go de RAM. Budget retenu : **2 graines × 300 000 itérations**,
avec instantanés à 100 000 et 200 000.

| Entraînement V3 | 100 000 it. | 200 000 it. | 300 000 it. | CPU total | Ensembles d'information | Regret moyen / it. (300k) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Graine 73001 | 3 336 s | 7 323 s | 11 199 s | **3 h 07** | 61 690 | 0,00125 |
| Graine 73002 | 3 330 s | 7 037 s | 10 630 s | **2 h 57** | 61 721 | 0,00123 |

Politique V3 : 682 Ko compressée (V2 : 111 Ko).

## 8. Évaluation finale : V2 et V3, avec et sans adaptation

Protocole fixé et commité **avant** la fin de l'entraînement de V3 et avant toute main finale
(`df0b464`) :
- graines neuves (121001–121003 / 131001–131003) ;
- 10 000 mains par graine, politique et adversaire, bouton alterné ;
- statistiques publiques exposées à tous, les agents non adaptatifs les ignorant ;
- 60 expériences, soit 600 000 mains.

L'audit a rejoué **chaque décision CFR** avec le même agent que le benchmark, adaptation
comprise, et toutes ont été reproduites à l'identique.

### bb/100 net (rake 5 %, plafond 3 BB, no-flop-no-drop), IC à 95 %

| Contre… | V2 | V2 + adaptation | V3 (73001) | V3 + adaptation | V3 graine 2 |
| --- | ---: | ---: | ---: | ---: | ---: |
| **HyperAggressive** | +386,5 [+325,3 ; +447,7] | **+517,8 [+426,5 ; +609,1]** | +132,3 [+74,1 ; +190,5] | +307,7 [+223,6 ; +391,8] | +214,1 [+151,6 ; +276,6] |
| **TightAggressive** | **+23,5 [+6,9 ; +40,0]** | +23,5 (identique) | +6,4 [−12,7 ; +25,6] | +6,4 (identique) | +0,1 [−18,9 ; +19,0] |
| **CallingStation** | +128,7 [+92,1 ; +165,4] | +128,7 (identique) | +205,1 [+156,7 ; +253,6] | +205,1 (identique) | **+266,5 [+217,3 ; +315,6]** |
| **EquityHeuristic** | **+138,7 [+101,1 ; +176,2]** | +138,7 (identique) | +55,9 [+10,2 ; +101,6] | +55,9 (identique) | +55,7 [+9,6 ; +101,8] |

Verdicts préenregistrés : toutes les politiques **battent** hyper, calling station et Equity
(IC entièrement positif et trois graines positives). Contre TAG, **V2 bat TAG sur ces graines**
(+18,8 / +22,8 / +28,8), mais V3 est non concluante.

### Différences appariées (mêmes donnes, main par main)

| Comparaison | Hyper | TAG | Station | Equity |
| --- | ---: | ---: | ---: | ---: |
| **V2 + adaptation − V2** | **+131,3 [+59,8 ; +202,8]** | 0,0 | 0,0 | 0,0 |
| V3 + adaptation − V3 | **+175,4 [+111,1 ; +239,8]** | 0,0 | 0,0 | 0,0 |
| **V3 − V2** | **−254,2 [−317,4 ; −191,0]** | −17,0 [−35,0 ; +1,0] | **+76,4 [+32,9 ; +119,9]** | **−82,8 [−126,5 ; −39,0]** |
| V3 + adaptation − V2 | −78,8 [−161,4 ; +3,8] | −17,0 [−35,0 ; +1,0] | +76,4 [+32,9 ; +119,9] | −82,8 [−126,5 ; −39,0] |
| V3 graine 2 − V3 graine 1 | **+81,9 [+20,9 ; +142,8]** | −6,3 [−23,7 ; +11,0] | **+61,3 [+14,8 ; +107,8]** | −0,2 [−45,0 ; +44,6] |

### Par position (bb/100, rake 5 %)

| Contre… | V2 bouton / BB | V2 + adaptation bouton / BB | V3 bouton / BB |
| --- | --- | --- | --- |
| Hyper | +583,7 / +189,2 | +677,5 / **+358,1** | +168,8 / +95,7 |
| TAG | +29,8 / +17,1 | identique | +7,3 / +5,5 |
| Station | +141,8 / +115,7 | identique | +288,2 / +122,1 |
| Equity | +126,6 / +150,7 | identique | +71,1 / +40,7 |

L'adaptation profite surtout à la **grosse blinde** contre l'hyper-agressif (+189 → +358).

### Fréquences d'action (moyenne de 3 graines)

| Contre… | Politique | VPIP | PFR | Fold BB vs relance | Relance flop | Fold face à mise flop / turn / river | Sorties d'arbre |
| --- | --- | ---: | ---: | ---: | ---: | --- | ---: |
| Hyper | V2 | 66 % | 43 % | 52 % | 23 % | 43 / 39 / 44 % | 10,8 % |
| Hyper | **V2 + adaptation** | **90 %** | 44 % | **10 %** | 25 % | **20 / 20 / 32 %** | 10,7 % |
| Hyper | V3 | 66 % | 49 % | 49 % | 37 % | 39 / 38 / 51 % | 10,1 % |
| Hyper | V3 + adaptation | 90 % | 51 % | 10 % | 34 % | 21 / 18 / 42 % | 9,3 % |
| TAG | V2 | 77 % | 51 % | 59 % | 46 % | 43 / 48 / 47 % | 0,0 % |
| TAG | V3 | 78 % | 49 % | 53 % | 57 % | 41 / 43 / 45 % | 0,0 % |
| Station | V3 | 59 % | 41 % | — | 58 % | 38 / 35 / 49 % | 1,3 % |
| Equity | V3 | 60 % | 43 % | 38 % | 51 % | 38 / 33 / 54 % | 4,7 % |

Le coût par décision reste de 1,6 à 2,3 ms pour toutes les variantes.

### Lecture

- **L'adaptation fonctionne et ne coûte rien ailleurs.** Contre un ouvreur très agressif, elle
  divise par 5 les abandons de la grosse blinde (52 % → 10 %), paie davantage et gagne +131 bb/100
  de plus. Contre
  les autres profils, elle ne s'active pas : la robustesse contre TAG est préservée **par
  construction**.
- **V3 ne remplace pas V2.** Elle est plus agressive postflop (relances au flop 37 % contre 23 %
  face à hyper) mais **paie moins à la river** (51 % de folds) et perd beaucoup de valeur contre les
  profils qui misent. Avec 6,3 fois plus d'ensembles d'information pour le même nombre d'itérations,
  chaque situation est moins entraînée. L'écart significatif entre les deux graines de V3 (+82 contre
  hyper, +61 contre station) confirme que **V3 n'a pas convergé**.
- **Les replis hors arbre persistent contre l'hyper-agressif** (environ 10 % avec 4 relances par
  street). Ils viennent surtout de séquences de relances préflop et postflop dont les tailles
  s'éloignent de l'abstraction : une piste pour la suite.
- **V2 contre TAG** : regrouper a posteriori les quatre jeux de graines indépendants (Missions 5 et 6,
  120 000 mains) donne **+9,8 bb/100 [+1,7 ; +17,9]**. C'est un indice favorable, mais il ne s'agit
  pas d'un test préenregistré, et un seul des quatre jeux est significatif à lui seul (+8,7 / +6,2 /
  +0,9 / +23,5).

## 9. Intégration aux salles et au Spectate

Après les tests fonctionnels :
- **CFR V2 · adaptive** devient l'adversaire présélectionné dans *Play with models* et *Spectate*.
  Les salles transmettaient déjà les statistiques publiques aux agents ; le Spectate les transmet
  désormais aussi.
- **CFR V3 · 300k (experimental)** est sélectionnable, avec la mention de ses performances plus
  faibles contre les profils agressifs.
- V1 200k, V1 20k et V2 300k restent disponibles et inchangées.
- `HyperAggressive` et `CallingStation` sont jouables en Spectate.

Tests d'intégration :
- partie complète via l'API contre `cfr-v1`, `cfr-v2`, `cfr-v2-adapt` et `cfr-v3` ;
- l'entrée adaptative lit bien les statistiques publiques de la requête : avec 9-6 en grosse
  blinde face à un ouvreur à 90 % de PFR, elle se couche dans au plus 8 cas sur 40, contre au moins
  30 sur 40 pour V2 ;
- tests navigateur réels : 6 mains jouées en cliquant contre l'adversaire par défaut, et un match
  Spectate CFR V2 · adaptive contre TAG.

## Tests exécutés

```bash
.venv/bin/python -m pytest -q
cd frontend && npm test && npm run build
PB_BASE_URL=http://127.0.0.1:8097 node tests/cfr-room.mjs
PB_BASE_URL=http://127.0.0.1:8097 node tests/spectate.mjs
```

- **704 tests Python réussis** (685 hérités de la mission 5 et 19 nouveaux), **26 tests frontend
  réussis**, compilation réussie, **2 tests navigateur réels réussis**.
- Nouveaux tests :
  - concordance des trois comptabilités de salle sur une partie agressive avec remises à zéro ;
  - audit en lecture seule ;
  - calibrage et confidentialité des profils hyper et calling station ;
  - overlay : redistribution, inertie sans preuve, défense de la grosse blinde, cartes cachées
    ignorées, statistiques publiques du benchmark ;
  - V3 : synchronisation jeton par jeton après export, niveau préflop dans les clés ;
  - protocoles : graines neuves et disjointes, plan final, analyse par position et par street ;
  - entrée de salle adaptative.
- Trois tests existants ont été ajustés volontairement :
  - la liste des modèles de salle inclut les nouvelles entrées CFR ;
  - le test d'audit de salle ne suppose plus une relance à chaque main (impossible face à un tapis) ;
  - les tests navigateur suivent le nouvel adversaire par défaut.
- Non-régression : des décisions V1 et V2 enregistrées en missions 4 et 5 se rejouent à l'identique
  après les modifications.

## Reproduction

```bash
cd backend
../.venv/bin/python -m pokerbench.mission6 run --plan baseline --output ../artifacts/repro/baseline
../.venv/bin/python -m pokerbench.mission6 analyze --plan baseline ../artifacts/repro/baseline --output ../artifacts/repro/baseline/analysis.json
for s in 73001 73002; do
  ../.venv/bin/python -m pokerbench.selfplay holdem --version 3 --iterations 300000 --seed $s \
    --every 10000 --snapshot 100000 --snapshot 200000 --output ../artifacts/repro/v3-$s
done
../.venv/bin/python -m pokerbench.mission6 run --plan final --output ../artifacts/repro/final
../.venv/bin/python -m pokerbench.mission6 analyze --plan final ../artifacts/repro/final --output ../artifacts/repro/final/analysis.json
```

**Versionné** :
- code et tests ;
- politiques V3 (`artifacts/mission6/policy-v3-*.json.gz`, avec les instantanés 100k et 200k de la
  graine 73001) et courbes d'entraînement ;
- plans, manifestes, `hands.csv` et `analysis.json` de la mesure de référence et de l'évaluation
  finale.

**Non versionné** : les journaux privés `decisions.jsonl` et le pilote exploratoire. Aucun secret.

## Limites

- Les 49 mains réelles n'ont pas pu être auditées, faute d'accès aux données.
- `HyperAggressiveAgent` est un modèle simplifié d'un joueur humain ; un humain agressif mais
  intelligent peut exploiter V2 autrement.
- L'adaptation n'utilise que le PFR public ; elle ne détecte ni les joueurs qui se couchent trop, ni
  les bluffeurs postflop.
- V3 est sous-entraînée ; aucune exploitabilité n'est mesurée dans le jeu réel ; rien de tout cela
  n'est une stratégie GTO du no-limit complet.

## Suite proposée

1. Auditer la vraie partie dès que son export est disponible (`room_audit.py`).
2. Entraîner V3 bien plus longtemps (au moins 1,5 million d'itérations, environ 12 h CPU), ou réduire
   son arbre, puis comparer à nouveau, avec une courbe d'apprentissage.
3. Étendre l'adaptation à d'autres statistiques publiques (fold face aux mises, agression postflop),
   ce qui suppose de les ajouter aux compteurs publics.
4. Réduire les replis hors arbre contre les relanceurs compulsifs (traduction des tailles préflop,
   plafond de relances).
5. Préenregistrer un test confirmatoire V2 contre TAG de 200 000 mains, ou avec donnes dupliquées.

Aucune automatisation sur un site de poker tiers n'a été ajoutée.
