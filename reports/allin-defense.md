# Défense face aux all-in répétés : variantes expérimentales de CFR V2 adaptative

**Conclusion : aucune variante n'est acceptée. CFR V2 · adaptive reste l'adversaire par défaut.**
Les variantes restent disponibles dans le code pour la recherche (`allin.py`, benchmark), mais ne
sont pas proposées dans les salles ni dans le Spectate.

## Motivation

Dans la session humaine de 49 mains (`reports/audit-49-mains.md`), l'humain a fait tapis dans 34
mains, et CFR V2 s'est couchée 29 fois sur 34. En moyenne sur toutes ses mains possibles, la
politique V2 paie un tapis de 200 BB préflop dans 12 à 14 % des cas. CFR V2 adaptative (overlay
fondé sur le PFR public) paie environ 25 % après 20 mains.

## Variantes étudiées (`backend/pokerbench/allin.py`)

`AllInAwareAgent` s'ajoute à CFR V2 adaptative, **sans la modifier** :

- **Activation plus rapide** : fréquence de tapis publique f = (tapis + 0,05 × 10) / (mains + 10),
  soit un a priori faible ; la règle agit dès f ≥ 15 %.
- **Montant réel et cote du pot** : face à un tapis préflop, ou à une mise d'au moins la moitié du
  tapis effectif, l'agent paie si son équité contre la range estimée est ≥ `à_suivre / (pot +
  à_suivre) + 2 points`.
- **Range estimée, deux hypothèses explicites**. Aucune fréquence de call n'est universelle :
  - `top` : l'adversaire pousse ses f % meilleures mains (adversaire sélectif) ;
  - `any` : il pousse n'importe quelles cartes (adversaire indiscriminé).
- L'équité contre la range est estimée par Monte Carlo (300 tirages), sans aucune carte cachée.
- Ailleurs, et quand f < 15 %, CFR V2 adaptative joue inchangée. Les tests vérifient l'identité
  action par action.

Un **compteur public d'all-in séparé** (`all_in`, `all_in_preflop`) est transmis **uniquement** aux
agents qui le demandent. Les statistiques publiques envoyées aux modèles LLM des salles et du
benchmark restent identiques, ce qui préserve leurs empreintes de décision.

Nouveau profil de test **ShoverAgent** : un hyper-agressif qui fait tapis préflop dans 78 % des cas
où il le peut, soit 68,4 % des mains où il agit (session réelle : 34 sur 49, 69 %).

### Contrefactuel : fréquence de call face à un tapis de 200 BB préflop

Moyenne sur 300 mains de CFR tirées au hasard, cote 49,7 % :

| Mains observées | Tapis observés | f estimé | CFR V2 | V2 adaptative | Variante `top` |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 10 | 1 | 0,07 | 11,2 % | 15,8 % | 15,8 % (inactive) |
| 10 | 3 | 0,17 | 11,2 % | 15,8 % | 7,0 % |
| 10 | 7 | 0,38 | 11,2 % | 15,8 % | 11,3 % |
| 30 | 21 | 0,54 | 11,2 % | 27,9 % | 23,3 % |
| 49 | 34 | 0,58 | 11,2 % | 32,8 % | 25,7 % |

Avec l'hypothèse `top`, la variante paie **moins** que V2 adaptative : contre une range sélective,
il faut payer plus serré. Les « 49 % » cités dans l'audit ne valent que si l'adversaire pousse
vraiment n'importe quelles cartes.

## Protocole (`backend/pokerbench/allin_eval.py`, commit `2b6afde`, fixé avant toute main)

- **Politiques** : `adapt` (CFR V2 adaptative, la référence), `allin-top`, `allin-any`, toutes sur
  la politique V2 300k.
- **Adversaires** : HyperAggressive, TAG, CallingStation, Equity, Shover.
- **Données** : graines inédites (171001–171003 / 181001–181003), 10 000 mains par graine, bouton
  alterné, **donnes identiques** pour les trois politiques, statistiques publiques et compteurs
  d'all-in exposés. Au total : **450 000 mains**.
- **Mesure** : bb/100 net à 5 % de rake (plafond 3 BB, no-flop-no-drop), IC à 95 % ; différences
  appariées main par main contre `adapt`.
- **Acceptation** : IC de l'écart contre Shover entièrement > 0 **et** aucun écart entièrement < 0
  contre les quatre autres profils. Sinon, V2 adaptative reste la version par défaut.

L'audit a rejoué chaque décision CFR avec le même agent que le benchmark : toutes ont été
reproduites, sans carte cachée dans les observations.

## Résultats

### bb/100 net (rake 5 %), IC à 95 %, 30 000 mains par case

| Contre… | V2 adaptative | `allin-top` | `allin-any` |
| --- | ---: | ---: | ---: |
| **Shover** | **+1 252,0 [+1 129,2 ; +1 374,8]** | +1 106,0 [+995,4 ; +1 216,6] | +1 228,1 [+1 097,9 ; +1 358,3] |
| HyperAggressive | +625,7 [+533,9 ; +717,5] | +626,4 | +625,0 |
| TightAggressive | +13,9 [−2,8 ; +30,6] | identique | identique |
| CallingStation | +116,0 [+80,3 ; +151,7] | identique | identique |
| EquityHeuristic | +142,4 [+105,7 ; +179,1] | identique | identique |

### Différences appariées contre V2 adaptative

| Variante | Shover | Hyper | TAG | Station | Equity | Décision |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `allin-top` | **−146,0 [−204,2 ; −87,8]** | +0,7 [−0,6 ; +2,0] | 0,0 | 0,0 | 0,0 | **refusée** (pire contre Shover) |
| `allin-any` | −23,9 [−79,7 ; +31,9] | −0,7 [−2,0 ; +0,6] | 0,0 | 0,0 | 0,0 | **refusée** (pas d'amélioration démontrée) |

### Réponses aux tapis préflop de Shover (20 473 tapis subis par politique)

| Politique | Paie | Fold de la BB face à une relance | Folds préflop | bb/100 bouton / BB |
| --- | ---: | ---: | ---: | --- |
| V2 adaptative | 39,0 % | 50 % | 30 % | +1 153,3 / +1 350,7 |
| `allin-any` | 44,4 % | 46 % | 27 % | +1 158,0 / +1 298,2 |
| `allin-top` | 30,1 % | 57 % | 34 % | +1 043,8 / +1 168,2 |

Contre TAG, CallingStation et Equity, la fréquence de tapis reste sous le seuil : les variantes jouent
**exactement** comme V2 adaptative (différence de 0,0). Contre HyperAggressive, qui fait rarement
tapis, l'effet est négligeable (±0,7 bb/100).

## Lecture

1. **V2 adaptative résiste déjà très bien à un pousseur compulsif** : +1 252 bb/100 contre Shover, en
   payant 39 % des tapis. Les 12 à 14 % mesurés pour V2 seule concernaient la politique sans adaptation.
2. **L'hypothèse sur la range domine tout.** Supposer un pousseur sélectif (`top`) fait trop se coucher
   contre un pousseur indiscriminé et coûte −146 bb/100. Supposer n'importe quelles cartes (`any`)
   correspond exactement à Shover, et pourtant n'apporte rien de mesurable : les calls ajoutés sont
   proches de l'équilibre (équité ≈ cote du pot), donc d'espérance presque nulle, avec une forte
   variance.
3. Contre un humain réel, la range de tapis est inconnue et probablement entre les deux hypothèses. Sans
   observer de mains abattues, choisir une hypothèse revient à parier sur le style adverse. Le gain
   potentiel mesuré ne justifie pas ce pari.

## Limites

- Shover est un modèle simple : tapis indiscriminés à fréquence fixe, sans adaptation à l'adversaire.
- Seuls les tapis préflop sont traités ; les tapis postflop restent gérés par l'overlay V2 adaptatif.
- L'IC contre TAG (+13,9 [−2,8 ; +30,6]) reste non concluant sur ces graines.

## Pistes

- Estimer la range de tapis à partir des **mains montrées à l'abattage** (information publique),
  plutôt que de la supposer.
- Tester un mélange des deux hypothèses pondéré par ces observations, sous protocole préenregistré.
