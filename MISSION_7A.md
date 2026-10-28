# Mission 7A — robopoker, Slumbot, Jev ↔ CFR et agent hybride

Branche : `claude/quirky-bardeen-1ddjmk`, repartie de `main` après la fusion de la PR #4.
La PR #5 (défense anti-all-in) reste séparée et non fusionnée ; rien ici n'en dépend.

## 1. Résumé

| Objectif | État |
| :-- | :-- |
| 1. Audit robopoker (abstraction, solver, `spar`) | Fait, en lecture seule (rien compilé ni exécuté) — §2 |
| 2. Éléments réutilisables sans remplacer PokerKit | Protocole Slumbot, discipline réseau, traduction pseudo-harmonique : réécrits en Python ; le reste écarté — §2.5 |
| 3. API Slumbot, règles, conditions | Règles documentées ; **aucune condition d'utilisation formelle trouvée**, site injoignable depuis cette session — §3 |
| 4. Interface Jev ↔ CFR sur les mêmes observations | `compare.py`, testé avec des conseillers locaux et simulés — §4 |
| 5. Agent hybride + méthode de sélection testable | `hybrid.py` (4 règles) + protocole préenregistré — §5 |
| 6. Coûts CPU et API | `costs.py` : CPU mesuré ; API calculée à partir de prix **supposés** — §6 |
| 7. Politiques et tests existants | Aucun fichier existant modifié ; suite complète verte — §8 |

Aucun entraînement, aucun appel payant, aucune partie sur slumbot.com. Le mode réel du client
Slumbot est verrouillé derrière une autorisation écrite explicite. CFR V2 adaptative reste
l'IA par défaut.

## 2. Diagnostic robopoker

Source : `github.com/krukah/robopoker`, commit `b6bf9e2` (24/10/2026), licence MIT,
version 3.0.0, 864 fichiers Rust. Le code a été cloné en profondeur 1 dans un dossier temporaire
isolé et seulement lu.

### 2.1 Architecture

Un espace de travail Rust de 29 crates, en trois étapes : abstraction calculée une fois →
« blueprint » entraîné par MCCFR → re-résolution en jeu. Le crate nommé `pokerkit` est un module
Rust interne (types, constantes, traduction) **sans rapport** avec la bibliothèque Python
PokerKit que nous utilisons. Le moteur de jeu est `kicker` (pots, all-in, égalités).

### 2.2 Abstraction

- Hold'em heads-up, 100 BB à l'entraînement (`STACK = 200`, `B_BLIND = 2`).
- Cartes : k-means hiérarchique de la river vers le preflop sur les mains isomorphes,
  distance EMD (Sinkhorn). 256 groupes au flop et au turn, histogrammes d'équité à 101 cases à la river.
- Tailles de mise (régime « Pluribus ») : 3-bet à 1×, 2× ou 3× le pot ; flop 1/4, 1/2, 1×, 2× ;
  turn et river 1/3, 1/2, 1×, 2× ; au plus 3 relances répétées.
- Coût : tables de 4 Ko (preflop) à **3,02 Go** (river), PostgreSQL obligatoire,
  entraînement annoncé sur 16 vCPU et 120 Go de RAM.

À comparer avec notre V2 : quelques dizaines de seaux calculés à la volée, une politique de
111 Ko, un cœur CPU.

### 2.3 Solver

- `Flagship = Tabular<NlheEncoder, LinearRegret, LinearWeight, PluribusSampling, 128>` :
  Linear CFR (DCFR(1,1,1), comme Pluribus), échantillonnage externe avec élagage des regrets,
  arbre construit dynamiquement.
- Re-résolution en jeu : sous-jeu à profondeur limitée (4 continuations biaisées) et résolution
  « sûre » sur 4 mondes de croyances.
- Option Deep CFR : réseaux à la place des tables.
- Traduction d'action : arrondi au plus proche, pseudo-harmonique (Ganzfried-Sandholm 2013)
  aléatoire ou déterministe, ou sans abstraction.

### 2.4 Client `spar` et banc d'essai `bout`

- `spar` : deux routes `POST new_hand` / `POST act`, sur `https://slumbot.com/slumbot/api`.
  Il relit la chaîne d'actions cumulative de Slumbot, reconstruit l'état quand le board grandit
  et ajoute le fold manquant quand les gains arrivent avant lui.
- Effet de bord : il convertit les mains de Slumbot à 200 BB vers un blueprint entraîné à 100 BB.
- `bout` : au plus 3 requêtes simultanées par défaut. En mode continu, il recule exponentiellement
  jusqu'à 5 minutes. Les erreurs sont comptées, jamais avalées ; une session en échec est remplacée.
- Intervalle de confiance calculé sur l'écart-type par main.

**Résultats publiés** (README, non reproduits ici) :
- contre Slumbot, la meilleure variante fait **−13,1 ± 14,0 bb/100 sur 86 000 mains** ;
  la politique jouée en argmax (« dirac ») sans recherche fait −28,4 ± 6,0 sur 480 000 mains ;
- les auteurs concluent que « la température d'échantillonnage, pas la recherche, est la perte
  dominante » ;
- leur suite de tests stratégiques (`litmus`) passe 34 contrôles sur 40.

### 2.5 Ce qu'on réutilise, ce qu'on écarte

**Réutilisé** (idées réécrites en Python, aucun code Rust importé) :

| Élément robopoker | Où chez nous |
| :-- | :-- |
| Grammaire Slumbot, chaîne cumulative, board qui grandit, fold implicite | `slumbot.py` |
| Discipline réseau : une session, rythme minimal, recul exponentiel, arrêt après échecs répétés | `slumbot.HttpTransport`, `SlumbotSession` |
| Traduction pseudo-harmonique (formule de l'article) | `translation.py`, testée, **non branchée** |
| Constat « argmax > échantillonnage » contre Slumbot | piste d'expérience (§7), non appliquée |
| Idée des tests stratégiques `litmus`, variance réduite AIVAT | pistes futures (§7) |

**Écarté** :

| Élément | Raison |
| :-- | :-- |
| Moteur `kicker` | PokerKit reste l'arbitre |
| Abstraction k-means/EMD, blueprint | Go de tables, PostgreSQL, 120 Go de RAM : c'est un entraînement massif |
| Re-résolution de sous-jeux, Deep CFR | Dépendent de ce blueprint |
| Serveur `portal`/`parlor`, authentification | Doublons de notre FastAPI |

Une liaison Rust↔Python ajouterait une chaîne de compilation entière pour aucun gain mesurable
à notre échelle.

**Différence de profondeur.** Notre benchmark se joue déjà à 200 BB en 50/100 avec 20 000 jetons,
soit le format exact de Slumbot. Nos politiques V2 sont entraînées à cette profondeur, alors que
robopoker convertit un blueprint à 100 BB.

## 3. Slumbot : API, règles, conditions

### 3.1 Ce qui est établi

Recoupement de trois sources : le client `spar` de robopoker, l'adaptateur communautaire
`aipoker-bot/slumbot-adapter`, et l'issue `ericgjackson/slumbot2019#49`.

- **Routes.** `POST /slumbot/api/new_hand {token?}` et `POST /slumbot/api/act {token, incr}`.
- **Réponse.** `token`, `client_pos`, `hole_cards`, `board`, `action` ; puis `winnings` en fin de
  main, et en général `bot_hole_cards`.
- **Format de jeu.** No-limit heads-up, blinds 50/100, 20 000 jetons remis à zéro à chaque main
  (200 BB), sans rake.
- **Position.** `client_pos` = 0 : nous sommes la grosse blind ; 1 : la petite blind (bouton).
  Slumbot alterne les positions.
- **Grammaire.** `k` check, `c` call, `f` fold, `bN` mise ou relance à un total N sur la rue
  (blinds comprises), `/` fin de rue.
- **Accès.** Pas de clé ni d'inscription. Partie anonyme ou connectée.

### 3.2 Ce qui n'est pas établi

- `slumbot.com` est **bloqué par la politique réseau de cette session** (résolution DNS refusée) :
  je n'ai pu lire ni le site, ni son `sample_api.py`, ni une éventuelle page de conditions.
- Aucune **condition d'utilisation formelle**, aucun **quota chiffré** n'a été trouvé.
- Le mainteneur répond le 12/10/2026, dans l'issue #49, à un autre chercheur qui prévoyait
  20 000 à 30 000 mains en une session séquentielle à ≥ 500 ms entre requêtes :
  « Your plan sounds fine », et prévient que le serveur peut saturer et qu'il faut alors
  ralentir. Cette réponse est informelle et ne s'adresse pas à nous : **ce n'est pas une
  autorisation pour ce projet**.

### 3.3 Avant tout benchmark réel

1. Écrire au mainteneur (Eric Jackson, via slumbot.com ou GitHub) pour décrire le plan :
   nombre de mains, une seule session, ≥ 500 ms entre requêtes, recul sur erreur, citation.
2. Obtenir une réponse écrite.
3. Lancer avec la référence de cette autorisation :
   `python -m pokerbench.slumbot --live-authorization "<référence>" --hands N`.
   Le client refuse toute référence vide et tout intervalle sous 0,5 s, et plafonne `N` au
   montant autorisé.
4. Autoriser `slumbot.com` dans les réglages réseau de l'environnement.

### 3.4 Ce qui est implémenté (`backend/pokerbench/slumbot.py`)

- **Rejeu PokerKit.** Chaque réponse est rejouée de zéro dans une main PokerKit en mode manuel,
  avec les cartes de Slumbot inconnues. Toute action refusée par PokerKit interrompt la main.
  Les relances hors grille (ex. `b237`) sont acceptées si PokerKit les accepte.
- **Ce que voit l'agent.** Uniquement l'observation filtrée de cette main, au format exact du
  benchmark (chip_unit 50, statistiques publiques VPIP/PFR mises à jour).
- **Contrôle des gains.** En fin de main, la main est rejouée avec information complète
  (cartes révélées du bot, ou cartes quelconques après un fold) : les `winnings` annoncés sont
  comparés au règlement calculé par PokerKit. Un abattage sans cartes révélées est marqué « non vérifiable ».
- **Simulateur local.** `OfflineSlumbot` parle le même protocole avec un bot local. Il permet un
  essai à blanc complet : `python -m pokerbench.slumbot --offline tag --hands 300 --output …`.
- **Essai à blanc.** CFR V2 adaptative, 300 mains contre chacun des profils TAG, hyper, station
  et equity :
  - 0 erreur ;
  - **1 200/1 200 règlements concordants** (`artifacts/mission7a/slumbot-offline-dryrun.json`) ;
  - ces 300 mains par profil valident le circuit, pas la force du bot (intervalles de ±200 à ±800 bb/100).

## 4. Interface Jev ↔ CFR (`backend/pokerbench/compare.py`)

**Format commun.** Chaque point de décision est la requête qu'une salle envoie à un modèle
(`Hand.request`) : observation filtrée du joueur actif et actions légales. Un test vérifie que
la requête reconstruite à partir d'une observation est identique, consigne comprise. Chaque
conseiller répond par des probabilités sur ces identifiants d'action.

**Conseillers disponibles :**

| Conseiller | Rôle | Coût |
| :-- | :-- | :-- |
| `CFRAdvisor` | Politique locale. Sa distribution abstraite est projetée sur les actions concrètes, overlay adaptatif compris. Un test montre que l'action jouée par l'agent est toujours dans le support de cette distribution (V1, V2, V2 adaptative, V3). | Gratuit |
| `RecordedAdvisor` | Réponses enregistrées, retrouvées par hash de requête : on réanalyse sans rappeler | Gratuit |
| `ProviderAdvisor` | Jev (ou tout modèle) via le `Provider` existant | Payant |

`ProviderAdvisor` refuse de se construire sans `allow_paid=True` et sans budget positif, et
s'arrête quand le budget est atteint. Il n'est pas exposé en ligne de commande : un appel payant
reste un acte explicite. Le `Provider` met déjà en cache chaque décision par identifiant, donc
une même requête n'est jamais payée deux fois.

**Métriques.** Accord sur l'action la plus probable, accord sur le type (fold / passif / agressif),
distance de variation totale. Ventilées par rue, par adversaire et selon qu'on fait face à une
mise, avec la liste des plus grands désaccords.

**Démonstration gratuite** sur 2 360 décisions synthétiques (800 mains locales, `collect`) :

| Paire comparée | Même action | Variation totale moyenne |
| :-- | --: | --: |
| V2 adaptative vs V2 | 92,4 % | 0,060 |
| V2 adaptative vs V3 | 54,3 % | 0,374 |

Pour V2 adaptative vs V2, les désaccords sont **tous** contre l'hyper-agressif (accord de 75,8 %
contre lui, 100 % contre les autres profils) : la comparaison isole exactement l'endroit où agit
l'overlay. Données : `artifacts/mission7a/compare-local.json`. Les requêtes synthétiques
(8,7 Mo) ne sont pas versionnées : elles se régénèrent à l'identique avec la graine.

## 5. Agent hybride Jev + CFR (`backend/pokerbench/hybrid.py`)

### 5.1 Règles de sélection

Chaque règle est pure, paramétrée à l'avance, et décide à partir de la seule distribution de CFR
(V2 adaptative).

| Règle | Consulte Jev | Joue |
| :-- | :-- | :-- |
| `cfr` | jamais | CFR (référence) |
| `advisor` | toujours | Jev |
| `gate(τ)` | si CFR sort de son arbre (fallback) ou si sa meilleure action pèse moins que τ | Jev quand il est consulté, sinon CFR |
| `mix(w)` | toujours | (1−w)·CFR + w·Jev |

- Si Jev échoue (délai, réponse invalide), l'agent joue CFR et compte l'échec : la main n'est
  jamais bloquée.
- L'agent tire avec son propre générateur aléatoire et passe par le pont `play_action`
  (PokerKit valide chaque action).
- Aucune de ces règles n'est une stratégie d'équilibre. Les probabilités de Jev sont des
  préférences exprimées par le modèle.

**Taux de consultation de `gate`**, mesuré sans aucun appel sur les 2 360 décisions :

| τ | 0,5 | 0,6 | 0,7 | 0,8 | 0,9 |
| :-- | --: | --: | --: | --: | --: |
| Taux de consultation | 23,3 % | 42,6 % | 52,5 % | 64,6 % | 73,6 % |

### 5.2 Protocole de validation proposé (à figer avant tout appel payant)

**Phase 0 — gratuite, faite.** Taux de consultation, coûts, circuit testé avec des conseillers
simulés.

**Phase 1 — payante, petite, sur ton accord.**
- 500 décisions tirées des requêtes synthétiques, stratifiées par rue, envoyées à Jev seul.
- Mesures : taux de réponses valides, latence, tokens réels, accord avec CFR.
- Coût attendu ≈ 2,3 CNY aux prix supposés (§6). Le `Provider` bloque temporairement environ
  40 CNY de budget pendant les appels.
- Ne conclut **rien** sur la force de jeu.

**Phase 2 — benchmark apparié local.**
- Bras : `cfr` (V2 adaptative) contre `gate(0,5)` en principal, et `mix(0,25)` en secondaire.
- Conditions : mêmes donnes, mêmes graines de politique, graines neuves, adversaires hyper,
  TAG, station et equity.
- Métrique : bb/100 net à 5 % de rake, différence appariée par main, IC 95 % sur blocs de deux mains.
- Décision :
  - un bras est accepté seulement si sa différence est entièrement au-dessus de zéro contre
    au moins un adversaire, et jamais entièrement en dessous contre un autre ;
  - sinon CFR V2 adaptative reste la référence.
- Taille :
  - pilote de 2 000 mains par adversaire pour mesurer l'écart-type apparié réel, puis N fixé par
    la formule de §6 avant la course principale ;
  - les réponses de Jev sont mises en cache : une reprise ne coûte rien.

**Phase 3 — Slumbot réel, seulement avec l'autorisation de §3.3.**
- Uniquement le bras accepté et la référence.
- Non apparié, car les donnes de Slumbot ne se rejouent pas.

## 6. Coûts (`backend/pokerbench/costs.py`, `artifacts/mission7a/costs.json`)

**Mesuré** :
- CFR V2 adaptative : **0,8 ms CPU par décision** (1,6 à 2,3 ms dans les missions 5-6 avec le
  pont complet) ;
- **2,95 décisions** du héros par main ;
- requêtes de 3,7 Ko en moyenne, 5,6 Ko au maximum ;
- 10 000 mains de CFR seul coûtent donc quelques secondes de CPU.

**Supposé — à remplacer par les vrais tarifs.**
- **Le dépôt ne contient aucun prix vérifié pour Jev.** L'entrée Jev hérite des valeurs par
  défaut de `Entry` : 2,16 CNY / M de tokens en entrée et 8,64 CNY / M en sortie.
- Hypothèses de calcul : 4 octets par token, 300 tokens de sortie.
- Résultat : **≈ 0,0046 CNY par décision consultée**. Le `Provider` réserve temporairement
  0,08 CNY par appel (8 192 tokens de sortie au maximum).

**Coût API d'un bras hybride**, aux prix supposés :

| Règle | 1 000 mains | 10 000 mains | 50 000 mains |
| :-- | --: | --: | --: |
| `cfr` | 0 | 0 | 0 |
| `gate(0,5)` | 3,2 CNY | 32 CNY | 158 CNY |
| `gate(0,7)` | 7,1 CNY | 71 CNY | 355 CNY |
| `mix` / `advisor` | 13,5 CNY | 135 CNY | 677 CNY |

**Mains nécessaires**, avec n = (1,96 · σ · 100 / demi-largeur)² :

| Demi-largeur de l'IC | ±10 bb/100 | ±20 bb/100 | ±50 bb/100 |
| :-- | --: | --: | --: |
| Slumbot, non apparié (σ ≈ 20,9 bb/main) | 167 799 | 41 950 | 6 712 |
| Local apparié (σ ≈ 15,9 bb/main) | 97 116 | 24 279 | 3 885 |

- Le σ de Slumbot est déduit de l'intervalle publié par robopoker (±14,0 sur 86 000 mains).
- Le σ local est celui de V3 contre V2 face à TAG (mission 6). Un hybride `gate` diffère moins
  de CFR que V3 : son σ apparié devrait être plus petit, d'où le pilote.

**Durée sur Slumbot.**
- Au moins 3,95 requêtes par main à 0,5 s d'intervalle : **≥ 5,5 h pour 10 000 mains**, et
  ≥ 23 h pour les ~42 000 mains d'un IC à ±20.
- La latence réelle du serveur s'ajoute et n'est pas mesurable d'ici.
- Slumbot ne coûte rien en API, mais le bras hybride y paie Jev à chaque consultation :
  42 000 mains en `gate(0,5)` ≈ 130 CNY aux prix supposés.

## 7. Plan d'intégration

1. **Fait ici** (sans coût) : client Slumbot avec simulateur, harnais de comparaison, agent
   hybride, modèle de coûts, traduction pseudo-harmonique.
2. **Sur ton accord, Jev** : renseigner le vrai tarif dans l'entrée Jev, puis lancer la phase 1
   (≈ 500 appels).
3. **Benchmark** :
   - ajouter un bras `hybrid` à `benchmark.make_agent` (une option de `Config`, comme
     `cfr_adaptive`), le conseiller étant injecté côté serveur ;
   - préenregistrer la phase 2 dans un module `mission7.py` sur le modèle de `allin_eval.py`.
4. **Sur autorisation écrite de Slumbot** : phase 3.
5. **Pistes gratuites, indépendantes de Jev** :
   - évaluer CFR V2 adaptative en argmax ou à température réduite (le constat robopoker), avec
     un protocole apparié préenregistré — attention, une politique pure est plus exploitable
     par un adversaire qui s'adapte ;
   - comparer la traduction pseudo-harmonique à notre « taille la plus proche » ;
   - ajouter des tests stratégiques façon `litmus` sur la politique V2.

Rien n'est branché dans les salles, le spectateur ou le benchmark officiel : l'interface
utilisateur et les résultats existants sont inchangés.

## 8. Fichiers, tests, commandes

**Nouveaux modules** :
- `backend/pokerbench/slumbot.py`
- `backend/pokerbench/compare.py`
- `backend/pokerbench/hybrid.py`
- `backend/pokerbench/costs.py`
- `backend/pokerbench/translation.py`

**Tests** : `backend/tests/test_mission7a.py`, 26 tests :
- grammaire et rejet par PokerKit ;
- règlement avec fold implicite ;
- 4 sessions hors ligne de 60 mains, avec et sans séparateurs de runout ;
- cartes du bot jamais visibles par l'agent ;
- autorisation obligatoire, arrêt après échecs ;
- requêtes identiques à celles des salles ;
- support de l'action jouée, pour 4 politiques ;
- conseiller payant explicite et plafonné, réponses enregistrées ;
- coût égal à la réserve du `Provider` ;
- règles hybrides, repli sur échec, mains complètes via le pont ;
- monotonie du taux de consultation ;
- traduction, arithmétique d'échantillonnage.

**Suite complète** : voir le compte rendu de la PR. Aucun fichier existant n'est modifié et
toutes les politiques `.json.gz` sont intactes.

**Commandes** (depuis `backend/`, toutes gratuites) :

```bash
python -m pokerbench.compare collect --hands 200 --seed 7 --output /tmp/requests.jsonl
python -m pokerbench.compare local /tmp/requests.jsonl --a cfr-v2-adapt --b cfr-v2 --output /tmp/cmp.json
python -m pokerbench.compare estimate /tmp/requests.jsonl --input-cny-per-million 2.16 --output-cny-per-million 8.64
python -m pokerbench.costs /tmp/requests.jsonl --input-cny-per-million 2.16 --output-cny-per-million 8.64 --output /tmp/costs.json
python -m pokerbench.slumbot --offline tag --hands 300 --output /tmp/slumbot-offline.json
```

## 9. Limites

- **Conditions Slumbot.** Non vérifiées sur le site, qui est injoignable d'ici ; l'API est décrite
  à partir de clients tiers.
- **Pas de test réel du client Slumbot.**
  - Points non confirmés face au vrai serveur : le format exact d'un runout après all-in (avec ou
    sans `/`) et la présence systématique de `bot_hole_cards`.
  - Les deux cas sont gérés : un runout dans les deux formats, et un abattage sans cartes marqué
    non vérifiable.
- **Prix de Jev.** Inconnu dans le dépôt : les montants de §6 sont des ordres de grandeur
  paramétrés, pas des devis.
- **Jev n'a jamais été appelé.** L'accord CFR/Jev, la latence et le taux de réponses valides
  restent à mesurer (phase 1).
- **Aucun résultat de force de jeu.** Les chiffres hors ligne servent seulement à valider le
  circuit.

Sources : [robopoker](https://github.com/krukah/robopoker) ·
[issue slumbot2019 #49](https://github.com/ericgjackson/slumbot2019/issues/49) ·
[aipoker-bot/slumbot-adapter](https://github.com/aipoker-bot/slumbot-adapter) ·
[slumbot.com](https://www.slumbot.com) (non consulté, bloqué par le réseau de la session).
