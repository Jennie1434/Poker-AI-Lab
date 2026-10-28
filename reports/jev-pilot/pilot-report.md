# Pilote Jev ↔ CFR V2 adaptative (Mission 7B)

Décisions prévues : 500 · réponses valides : 500 · erreurs : 0
Modèles servis : {'jev-1.14.0': 500}

Latence : médiane 0.52 s, p90 0.68 s
Tokens d'entrée facturés : 989495 (moyenne 1979)
Coût prévu (borne haute) : 0.0899 USD

## Accord

| Périmètre | Décisions | Même action | Même type | Variation totale |
| :-- | --: | --: | --: | --: |
| Tout | 500 | 57.2% | 59.8% | 0.479 |
| street = flop | 150 | 58.7% | 58.7% | 0.445 |
| street = preflop | 150 | 46.7% | 55.3% | 0.511 |
| street = river | 100 | 66.0% | 66.0% | 0.469 |
| street = turn | 100 | 62.0% | 62.0% | 0.489 |
| opponent = equity | 156 | 66.0% | 68.6% | 0.451 |
| opponent = hyper | 147 | 44.9% | 46.9% | 0.568 |
| opponent = station | 164 | 61.0% | 62.2% | 0.425 |
| opponent = tag | 33 | 51.5% | 63.6% | 0.476 |
| facing_bet = False | 284 | 68.0% | 68.0% | 0.394 |
| facing_bet = True | 216 | 43.1% | 49.1% | 0.590 |

Masse moyenne que Jev place sur l'action préférée de CFR : 34.6%

## Types d'action (CFR → Jev)

| CFR → Jev | Décisions |
| :-- | --: |
| passive→passive | 244 |
| aggressive→passive | 119 |
| passive→fold | 60 |
| fold→fold | 42 |
| aggressive→aggressive | 13 |
| fold→passive | 13 |
| aggressive→fold | 8 |
| passive→aggressive | 1 |

## Plus grands désaccords

| Rue | Pos. | Cartes | Board | Pot / à payer | Historique | CFR | Jev | VT |
| :-- | :-- | :-- | :-- | :-- | :-- | :-- | :-- | --: |
| river | BB | 4c 8d | 2d 8h 7d Qc 8c | 500 / 100 | 2:call 1:check 1:check 2:check 1:check 2:raise100 1:call 1:check 2:raise100 | raise_to_700 99%, raise_to_19800 1% | call 43%, fold 34% | 0.95 |
| river | BB | Qs Js | Ks 5d Ad Tc 4d | 2500 / 500 | 2:call 1:check 1:check 2:check 1:raise200 2:raise400 1:call 1:raise500 2:raise1000 | raise_to_19500 100%, call 0% | call 41%, fold 27% | 0.90 |
| preflop | BB | 9c 6d | — | 400 / 200 | 2:raise300 | call 100%, raise_to_900 0% | fold 57%, call 14% | 0.86 |
| preflop | BB | 8s 8d | — | 500 / 300 | 2:raise400 | raise_to_1200 92%, raise_to_20000 7% | call 24%, raise_to_700 22% | 0.85 |
| preflop | BTN/SB | Qs 5c | — | 900 / 300 | 1:raise300 2:raise600 | call 100%, raise_to_20000 0% | fold 47%, call 15% | 0.85 |
| turn | BTN/SB | 5s 5c | 6s Qd 4d 3h | 800 / 200 | 1:raise300 2:call 2:check 1:check 2:raise200 | raise_to_1200 88%, call 11% | call 38%, fold 27% | 0.84 |
| flop | BB | Ad Js | 6s 9c 7h | 8400 / 3600 | 2:raise400 1:raise1200 2:raise2400 1:call 1:check 2:raise3600 | fold 100%, call 0% | call 31%, fold 16% | 0.84 |
| preflop | BTN/SB | Jh 3s | — | 300 / 100 | 1:call 2:raise200 | call 94%, raise_to_600 6% | fold 64%, call 14% | 0.84 |
| turn | BTN/SB | 9h Kc | 4c 6h 3s Js | 1800 / 600 | 1:raise200 2:raise500 1:call 2:raise100 1:call 2:raise600 | fold 97%, call 3% | call 39%, fold 13% | 0.84 |
| preflop | BB | Th As | — | 400 / 200 | 2:raise300 | raise_to_900 92%, raise_to_20000 7% | call 25%, raise_to_500 17% | 0.83 |
| preflop | BB | Kh 9d | — | 300 / 100 | 2:raise200 | raise_to_600 87%, call 12% | call 27%, fold 24% | 0.82 |
| river | BTN/SB | Qs 5c | Jd Ah 8h 9s Td | 1000 / 0 | 1:raise300 2:call 2:raise100 1:call 2:raise100 1:call 2:check | raise_to_1500 56%, raise_to_1000 24% | check 56%, raise_to_100 11% | 0.80 |
| river | BTN/SB | 2c 6s | 2d 5h Qs 6d Ad | 400 / 0 | 1:call 2:check 2:check 1:check 2:check 1:raise100 2:call 2:check | raise_to_600 58%, raise_to_400 21% | check 60%, raise_to_100 11% | 0.80 |
| river | BTN/SB | Qc 6c | Td 2s 5h 3s 7c | 400 / 0 | 1:raise200 2:call 2:check 1:check 2:check 1:check 2:check | raise_to_600 49%, raise_to_200 25% | check 61%, raise_to_100 12% | 0.80 |
| preflop | BB | 8s 5d | — | 300 / 100 | 2:raise200 | call 99%, fold 1% | fold 58%, call 19% | 0.80 |

Un désaccord n'indique pas qui a raison : seul le benchmark apparié (mission7.py) mesure l'effet en jetons.
