# Pilote Jev 1.14.0 ↔ CFR V2 adaptative — analyse complémentaire

Sources :
- les 500 réponses Jev du pilote, déjà enregistrées : **aucun nouvel appel** ;
- les distributions de CFR V2 adaptative sur les mêmes requêtes.

Code : `backend/pokerbench/pilot_review.py`. Données agrégées : `pilot-review.json`.
Les réponses brutes et le registre des appels ne sont pas publiés (`data/pilot7b/`, ignoré par git).

**Familles d'action** : fold ; check/call ; bet/raise (toutes tailles confondues).

## 1. Correction de la première synthèse

Le premier rapport comparait l'action **individuelle** la plus probable. Jev y préférait une
mise ou une relance dans 14 décisions seulement, contre 140 pour CFR, d'où la conclusion
« Jev est nettement plus passif ».

**Au niveau des familles, c'est faux.**

| Famille préférée | CFR | Jev |
| :-- | --: | --: |
| bet/raise | 171 | **242** |
| check/call | 281 | 168 |
| fold | 48 | 90 |

| Masse moyenne | CFR | Jev | Réponse uniforme |
| :-- | --: | --: | --: |
| fold | 0,10 | 0,14 | — |
| check/call | 0,54 | 0,41 | — |
| bet/raise | 0,36 | **0,45** | 0,81 |

En moyenne, **Jev est un peu plus agressif que CFR**, pas moins. Sa passivité apparente venait
de la façon de compter (voir §3).

## 2. Accord par famille

| Périmètre | Décisions | Accord (action) | Accord (famille) | CFR fold / call / relance | Jev fold / call / relance |
| :-- | --: | --: | --: | :-- | :-- |
| Tout | 500 | 57 % | 50 % | 0,10 / 0,54 / 0,36 | 0,14 / 0,41 / 0,45 |
| Preflop | 150 | 47 % | 53 % | 0,09 / 0,52 / 0,39 | **0,23** / 0,33 / 0,44 |
| Flop | 150 | 59 % | 41 % | 0,10 / 0,58 / 0,33 | 0,11 / 0,42 / 0,47 |
| Turn | 100 | 62 % | 50 % | 0,11 / 0,50 / 0,39 | 0,09 / 0,45 / 0,46 |
| River | 100 | 66 % | 59 % | 0,12 / 0,56 / 0,33 | 0,11 / 0,48 / 0,41 |
| Sans mise à payer | 284 | 68 % | 60 % | 0,00 / 0,57 / 0,43 | 0,00 / 0,50 / 0,50 |
| Face à une mise | 216 | 43 % | 37 % | 0,23 / 0,51 / 0,26 | **0,32** / 0,29 / **0,39** |
| vs hyper | 147 | 45 % | 31 % | 0,13 / 0,64 / 0,22 | **0,27** / 0,33 / 0,40 |
| vs equity | 156 | 66 % | 58 % | 0,10 / 0,54 / 0,36 | 0,09 / 0,44 / 0,47 |
| vs station | 164 | 61 % | 62 % | 0,06 / 0,49 / 0,44 | 0,06 / 0,47 / 0,47 |
| vs TAG | 33 | 52 % | 36 % | 0,13 / 0,34 / 0,53 | 0,19 / 0,36 / 0,45 |

**Pourquoi l'accord par famille est plus bas que l'accord par action.** Souvent, les deux
préfèrent la même action individuelle (par exemple `call`), mais Jev met plus de masse sur
l'ensemble de ses relances que sur ce `call`.

**Ce qui distingue vraiment Jev :**
- face à une mise, il se couche plus (0,32 contre 0,23) et relance plus (0,39 contre 0,26) ;
  il suit beaucoup moins (0,29 contre 0,51) ;
- preflop, il se couche deux fois et demie plus souvent ;
- contre l'hyper-agressif, il se couche deux fois plus. C'est précisément là où l'overlay
  adaptatif de CFR gagne le plus (mission 6) en suivant davantage.

## 3. Répartition entre plusieurs tailles de relance

| Mesure | CFR | Jev |
| :-- | --: | --: |
| Tailles de relance proposées en moyenne | 6,1 | 6,1 |
| Tailles réellement utilisées (≥ 1 %) quand la famille relance a > 5 % | 2,3 | **6,1** |
| Part de la plus grosse taille dans la masse de relance | — | **36 %** |
| Décisions où l'action individuelle préférée est passive mais la famille préférée est bet/raise | — | **228** |
| Spots où CFR relance (famille), et Jev aussi : par action individuelle | 171 | 13 |
| Spots où CFR relance (famille), et Jev aussi : par famille | 171 | **107** (63 %) |
| Masse de relance dans ces 171 spots | 0,75 | 0,51 |

**Conclusion.** La répartition sur ~6 tailles explique **l'essentiel** de la passivité apparente.
- Elle rend compte de 94 des 107 spots où les deux relancent au niveau familial.
- Elle explique la grande majorité des 119 cas « CFR relance → Jev passif » du premier rapport.
- Il reste un écart réel, mais modéré : dans les spots où CFR relance, Jev relance avec 0,51
  de probabilité contre 0,75 pour CFR.

**Uniformité.**
- La masse de relance de Jev n'est pas un simple effet d'indifférence : elle reste bien
  au-dessous de ce que donnerait une réponse uniforme (0,45 contre 0,81).
- Ses relances et ses folds suivent l'équité à peu près comme ceux de CFR :
  - corrélation relance/équité : +0,36 pour Jev, +0,30 pour CFR ;
  - corrélation fold/équité face à une mise : −0,46 pour Jev, −0,50 pour CFR.
- Mais ses distributions sont **beaucoup plus étalées** :
  - entropie normalisée 0,77 contre 0,34 ;
  - probabilité maximale moyenne 0,46 contre 0,72 ;
  - confiance déclarée 0,37.
- Jouer « comme Jev » revient donc à beaucoup randomiser, y compris entre des tailles de
  relance très différentes (de la min-relance au tapis).

## 4. Mains fortes et relances river

**Force de main.** Elle est mesurée par :
- la combinaison faite (treys), comptée comme forte à partir de deux paires ;
- l'équité contre une main aléatoire (Monte-Carlo à graine fixe), ou la table exacte preflop.

**Folds face à une mise, par tranche d'équité**

| Équité (vs main aléatoire) | Décisions | Fold CFR | Fold Jev | Relance CFR | Relance Jev |
| :-- | --: | --: | --: | --: | --: |
| 0-20 % | 9 | 0,80 | 0,47 | 0,09 | 0,26 |
| 20-40 % | 46 | 0,48 | 0,41 | 0,18 | 0,31 |
| 40-60 % | 107 | 0,14 | **0,33** | 0,26 | 0,39 |
| 60-80 % | 42 | 0,10 | **0,21** | 0,35 | 0,49 |
| 80-100 % | 12 | 0,08 | **0,23** | 0,37 | 0,38 |

- **Jev se couche trop avec les mains moyennes et fortes.** Il garde 21 à 33 % de fold là où
  CFR est à 8-14 %.
- **Jev relance plus souvent les mains faibles.**
- Mains fortes face à une mise (25 décisions) : fold moyen 0,27 pour Jev contre 0,17 pour CFR.
- Fold ≥ 25 % avec une main forte : **12 décisions pour Jev**, 4 pour CFR.

**Relances river.** Dans 30 spots river, CFR relance à ≥ 50 % (17 avec une main forte) :
- masse de relance moyenne : 0,77 pour CFR, 0,46 pour Jev ;
- avec des mains quasi imbattables (full, couleur, quinte, quinte flush), Jev checke 32 à 56 %
  du temps sans mise à payer. C'est de la valeur laissée sur la table.

## 5. Les 15 plus gros désaccords (variation totale)

| # | Situation | CFR (fold/call/relance) | Jev | Lecture |
| --: | :-- | :-- | :-- | :-- |
| 1 | River, brelan de 8 (8♦4♣), face à 100 dans 500 | 0 / 0 / **1,00** | 0,34 / 0,43 / 0,23 | **Erreur nette de Jev** : 34 % de fold avec 96 % d'équité, pour 100 à payer dans un pot de 500 |
| 2 | River, quinte à l'As (Q♠J♠), face à 500 dans 2500 | 0 / 0 / **1,00** | 0,27 / 0,41 / 0,32 | **Erreur nette de Jev** : 27 % de fold avec une main presque maximale, pour 500 à payer dans 2 500 |
| 3 | Preflop BB, 9♣6♦, face à une relance à 300 | 0 / **1,00** / 0 | **0,57** / 0,14 / 0,29 | Défense de BB : CFR suit (prix 33 %, équité 44 %) ; Jev se couche |
| 4 | Preflop BB, 8♠8♦, face à 400 | 0 / 0,01 / **0,99** | 0,12 / 0,24 / **0,64** | **Artefact de tailles** : les deux 3-bettent en famille (écart familial 0,35) |
| 5 | Preflop BTN, Q♠5♣, face à un 3-bet | 0 / **1,00** / 0 | **0,47** / 0,15 / 0,38 | Jev se couche, mais garde 38 % de 4-bet : distribution incohérente |
| 6 | Turn, 5♠5♣ (paire + tirage quinte par les deux bouts), face à 200 dans 800 | 0 / 0,11 / **0,89** | 0,27 / 0,38 / 0,35 | Jev se couche 27 % avec paire + tirage, pour 200 à payer dans un pot de 800 |
| 7 | Flop, A♦J♠ sans paire, face à 3 600 dans 8 400 après 4 relances | **1,00** / 0 / 0 | 0,16 / 0,31 / **0,53** | **Jev relance du vent** face à une grosse mise ; CFR se couche |
| 8 | Preflop BTN, J♥3♠, limp puis relance à 200 | 0 / **0,94** / 0,06 | **0,64** / 0,14 / 0,22 | Jev se couche après avoir limpé, pour 100 à payer dans un pot de 300 |
| 9 | Turn, K♥9♣ sans paire, face à 600 dans 1 800 | **0,97** / 0,03 / 0 | 0,13 / 0,39 / **0,48** | **Jev relance du vent** ; CFR se couche |
| 10 | Preflop BB, A♠T♥, face à 300 | 0 / 0,01 / **0,99** | 0,13 / 0,25 / **0,62** | **Artefact de tailles** (écart familial 0,37) |
| 11 | Preflop BB, K♥9♦, face à 200 | 0,01 / 0,12 / **0,87** | 0,24 / 0,27 / **0,49** | Surtout un artefact de tailles (écart familial 0,38) ; Jev se couche quand même 24 % |
| 12 | River, quinte (Q♠5♣ sur J-A-8-9-T), sans mise | 0 / 0 / **1,00** | 0 / **0,56** / 0,44 | Valeur manquée par Jev |
| 13 | River, deux paires (2♣6♠), sans mise | 0 / 0 / **1,00** | 0 / **0,60** / 0,40 | Valeur manquée par Jev |
| 14 | River, hauteur Dame (Q♣6♣), sans mise | 0 / 0,04 / **0,96** | 0 / **0,61** / 0,39 | Bluff de CFR ; Jev checke : défendable |
| 15 | Preflop BB, 8♠5♦, face à 200 | 0,01 / **0,99** / 0,01 | **0,58** / 0,19 / 0,23 | Défense de BB, comme le n° 3 |

**Bilan des 15 :**
- 3 sont **surtout des artefacts de tailles** (n° 4, 10, 11) ;
- 4 sont des **folds de mains fortes ou à forte cote** par Jev (n° 1, 2, 6, 8) ;
- 4 sont des **folds de défense preflop** par Jev (n° 3, 5, 15, et en partie 11) ;
- 2 sont des **relances sans main face à une grosse mise** par Jev (n° 7, 9) ;
- 3 sont des **mises river** que Jev ne fait pas (n° 12, 13 pour la valeur ; n° 14 est un
  bluff de CFR).

**Folds de mains fortes chez Jev (fold ≥ 25 %).** Sur 12 cas, plusieurs sont nets :
- brelan de 2 face à 3 150 dans 7 350 : fold 0,63 ;
- brelan de 2 face à 1 000 dans 4 000 : fold 0,31 ;
- couleur face à 800 dans 3 200 : fold 0,32 ;
- les deux exemples n° 1 et 2.

**CFR n'est pas exempte.** Elle a 4 cas comparables, par exemple :
- deux paires (dont une au board) jetées face à 6 300 dans 14 700 après une guerre de relances ;
- un brelan de 8 entièrement au board (le joueur n'a que le kicker Roi) jeté face à une relance river ;
- deux paires dont la paire d'As est au board, jetées au flop.

Ces folds sont plus défendables face à une telle agressivité, et ces « mains fortes » le sont
moins qu'elles n'en ont l'air (voir les limites), mais ils ne sont pas prouvés corrects.

## 6. La réponse rejetée : anomalie de l'API ou contrainte de notre validation ?

| Élément | Valeur |
| :-- | :-- |
| Situation | preflop, 8 actions légales |
| Réponse | `choice = fold` avec p(fold) = 0,25, alors que p(call) = 0,26 (maximum) ; confiance 0,15 |
| Règle officielle (schéma TypeSafe) | `choice` = « the choice with the highest probability » |
| Notre règle (`validate_answer`) | p(choice) ≥ max − 10⁻⁸ ; sinon rejet et nouvelle tentative (3 au maximum) |
| Suite | nouvelle tentative acceptée ; coût du rejet ≈ 0,00008 USD |

**C'est une anomalie de l'API.**
- Jev renvoie des probabilités arrondies au centième (488 réponses sur 500 ; les 12 autres ont
  été renormalisées par notre validation).
- Un arrondi monotone ne peut pas faire passer devant `call` une action plus probable : le
  `choice` contredit donc les propres probabilités de la réponse, et le schéma officiel.
- Ce n'est pas un problème d'égalité. Les 5 réponses acceptées dont le maximum est partagé ont
  toutes un `choice` parmi les actions à égalité ; notre validation les accepte.
- Fréquence : 1 sur 501 (0,2 %), sur une décision presque à pile ou face.

**Notre validation stricte est voulue.**
- Dans les salles, le runner joue le `choice` (`runner.py`).
- Accepter cette réponse aurait fait jouer `fold` alors que Jev préférait `call`.
- Je recommande de **garder la règle**. Le coût d'une nouvelle tentative est négligeable.

**Biais introduit.** La nouvelle tentative remplace une réponse incohérente par un nouveau
tirage du modèle. L'effet sur les statistiques est négligeable (1 cas).

## 7. Limites

- **Force de main approximative.** La combinaison faite compte les paires du board : 2♥2♦ sur
  K-4-4 est classé « deux paires ». L'équité contre une main aléatoire n'est pas l'équité contre
  la range réelle de l'adversaire, d'où les colonnes d'équité à côté des classes.
- **Biais de sélection des points de décision.** Ils viennent des trajectoires de CFR
  elle-même, sur des donnes synthétiques. Jev n'a jamais joué ses propres trajectoires.
- **Peu de décisions contre TAG** (33).
- **CFR n'est pas une vérité.** C'est une politique abstraite (seaux d'équité Monte-Carlo, tailles
  discrètes). Un désaccord n'est donc pas une erreur de Jev, sauf dans les cas où la théorie est
  sans ambiguïté (cotes 1 contre 5 ou 6 avec plus de 90 % d'équité).
- **Une seule version** (`jev-1.14.0`), une seule réponse par décision : la variabilité d'un
  tirage à l'autre n'est pas mesurée.
- **Rien ici ne mesure de bb/100.** Seul le benchmark apparié le fera.

## 8. Ce que cela implique pour l'agent hybride `gate(0.5)`

- **Où agirait Jev.** La règle ne consulte Jev que là où CFR hésite. Ses distributions
  très étalées y remplaceraient un mélange concentré (2-3 tailles) par un mélange sur ~6
  tailles, plus de folds face aux mises et moins de valeur à la river.
- **Signaux défavorables observés :** folds de mains fortes à forte cote, sur-fold preflop
  face à l'hyper-agressif, relances sans main face à de grosses mises.
- **Signal qui pourrait aider :** Jev relance un peu plus en moyenne, ce qui pourrait payer
  contre station (accord de 62 % en famille).
- **Pistes moins coûteuses à tester d'abord :**
  - un hybride « par famille » : Jev choisit la famille, CFR la taille ;
  - un filtre de cohérence qui interdit à Jev de se coucher avec plus de 80 % d'équité face à
    une cote favorable.

Ces deux variantes devraient être préregistrées avant toute course payante. CFR V2 adaptative
reste la référence.
