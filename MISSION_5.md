# Mission 5 — jouer contre notre IA, puis abstraction CFR V2

Repris depuis `main` après la fusion de la PR #1. Rapports relus : `MISSION_4.md`,
`MISSION_3.md`, `BENCHMARK_LAB.md`, `AUDIT_POKER_AI_LAB.md`. PokerKit reste l'unique
autorité sur les cartes, les actions légales et les gains. Les politiques V1 de la
mission 4 ne sont pas modifiées. Leur comportement est vérifié identique : 53 405
décisions enregistrées en mission 4 ont été rejouées avec le nouveau code, avec les
mêmes actions et les mêmes taux de repli.

> **Rapport en cours** : la table jouable et l'abstraction V2 sont livrées ; entraînements V2 et comparaison contre TAG en cours. Les sections marquées « à venir » seront complétées.

@@SYNTHESE@@

## Ordre de livraison

| Commit | Contenu |
| --- | --- |
| `e673c84` | **Table jouable** humain contre CFR dans les salles privées, historique, statistiques, test navigateur réel |
| `710fc89` | Abstraction **V2** et **protocole de comparaison V1/V2 figé** avant toute main d'évaluation |
| (dernier commit) | Entraînements V2, comparaison contre TAG, rapport |

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
  `CFR V1 · 20k` (instantané précoce, plus faible)@@V2_ENTRY@@. Chaque entrée porte
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

- `backend/tests/test_cfr_rooms.py` (6 tests, avec le vrai `Provider` et la vraie politique) :
  - enregistrement des politiques, et absence dans le roster du benchmark ;
  - refus des salles CFR multi-joueurs ou SNG ;
  - **partie complète via l'API** (4 mains), avec cartes adverses cachées à chaque étape ;
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

*(à venir)*
@@TRAINING@@

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

*(à venir)*
@@RESULTATS@@
