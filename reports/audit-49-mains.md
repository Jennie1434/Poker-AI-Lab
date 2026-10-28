# Audit de la session humaine de 49 mains contre CFR V2

Comparaison entre l'audit indépendant fourni par la propriétaire de la salle et
`backend/pokerbench/room_audit.py`, exécuté en lecture seule sur son export local
`GET /api/rooms/<id>/history?limit=200` (empreinte SHA-256 identique avant et après l'analyse).
**L'export personnel n'est pas versionné** ; ce rapport ne contient que des agrégats, sans cartes
ni détail main par main.

## Résultats

| Mesure | Audit de la propriétaire | `room_audit.py` | Accord |
| --- | --- | --- | --- |
| Mains | 49 | 49 | oui |
| Mains gagnées humain / CFR V2 | 44 / 5 | 89,8 % / 10,2 % | oui |
| Gain net | 0 / 0 BB | 0,0 / 0,0 BB | oui |
| Gains bruts / pertes brutes (chacun) | +453 / −453 BB | +453 / −453 BB | oui |
| VPIP / PFR humain | 91,8 % / 87,8 % | 91,8 % / 87,8 % | oui |
| VPIP / PFR CFR V2 | 55,1 % / 28,6 % | 55,1 % / 28,6 % | oui |
| All-in humains | 34 (32 préflop, 2 flop) | 34 (32 préflop, 2 flop) | oui |
| Réponse de CFR V2 à ces all-in | 29 folds, 5 calls | 29 folds, 5 calls | oui |
| Folds de CFR V2 par street | 36 / 4 / 1 / 1 | 36 / 4 / 1 / 1 | oui |
| Mains aux cartes des deux joueurs révélées | 7, dont 5 gagnées par CFR V2 | 7, dont 5 gagnées par CFR V2 | oui |
| Pots disputés ≥ 60 BB | — (avertissement sur le champ `pot`) | **35 avant correction, 6 après** | corrigé |

Mesures complémentaires de l'outil :
- grosse blinde de CFR V2 face à une ouverture : 17 folds sur 23 (73,9 %) ;
- agression postflop de l'humain : 9 mains, dont 7 où sa main finale révélée ne dépassait pas une
  paire.

## Correction apportée

Le champ `pot` de l'export est le plus gros pot affiché pendant la main, tapis non payé compris.
L'outil s'en servait pour classer les tailles de pot, et annonçait donc 35 « gros pots » au lieu
de 6. Il utilise désormais le **pot réellement disputé** : deux fois la plus petite mise totale,
blinds comprises. L'export de l'historique contient aussi un champ explicite `contested_pot`. Un
test reproduit le cas d'un tapis non payé suivi d'un fold.

## Analyse contrefactuelle des folds face aux tapis

Aucune carte cachée de la partie n'est utilisée. Sur toutes les mains possibles de CFR, face à un
tapis de 200 BB préflop :

| Situation | CFR V2 paie | CFR V2 adaptative paie (après 20 mains) |
| --- | ---: | ---: |
| CFR en grosse blinde, tapis du bouton | 12,1 % | 24,7 % |
| CFR limpe au bouton, tapis de la grosse blinde | 13,8 % | 25,4 % |

Dans la partie réelle, CFR V2 a payé 5 tapis sur 34 (14,7 %), ce qui est cohérent avec sa politique.
Si l'adversaire poussait **n'importe quelle main**, 49,3 % des mains auraient au moins l'équité
requise (49,8 %). Ce chiffre dépend entièrement de cette hypothèse sur la range adverse : il ne
constitue pas une fréquence de call optimale en général.

## Limites

49 mains ne permettent de juger ni le joueur ni CFR V2 : contre un joueur hyper-agressif, l'IC à 95 %
d'une partie de cette taille dépasse ±1 000 bb/100. La session teste la résistance aux tapis
préflop, pas le jeu postflop. Les cartes de CFR ne sont pas visibles lorsqu'elle se couche.
