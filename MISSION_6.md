# Mission 6 — corriger le jeu trop défensif de CFR V2

Repris depuis `main` (Missions 1 à 5). PokerKit reste l'unique autorité sur les cartes, les
actions légales et les gains. **V1 et V2 sont conservées intégralement** : leurs fichiers de
politique ne sont pas modifiés, et leurs décisions enregistrées lors des Missions 4 et 5 se
rejouent à l'identique avec le code de cette mission. Aucune intégration à un site tiers.

> **Rapport en cours** : diagnostic, profils de test, adaptation et V3 sont livrés ; l'évaluation finale V2/V3 est en cours.

@@SYNTHESE@@

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

@@RESULTATS@@
