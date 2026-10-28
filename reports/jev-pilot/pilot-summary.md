# Pilote Jev 1.14.0 ↔ CFR V2 adaptative — synthèse

Exécuté le 28/10/2026 selon le plan préenregistré (`artifacts/mission7b/pilot-plan.jsonl.gz`,
SHA-256 du contenu `1502acf0…`) : 500 décisions synthétiques (150 preflop, 150 flop,
100 turn, 100 river). Rapport détaillé : `pilot-report.md` ; données agrégées : `pilot-analysis.json`.
Les réponses brutes et le registre des appels restent hors du dépôt (`data/pilot7b/`, ignoré par git).

## 1. Vérification (10 appels)

**10 réussites sur 10, aucun échec.** Contrôles effectués :
- authentification ;
- modèle servi `jev-1.14.0` ;
- structure de la réponse : probabilités sur toutes les actions légales, `choice` légal, `confidence` présente ;
- champs `usage` ;
- facturation = tokens d'entrée × 0,042 USD/M, sortie à 0.

Le pilote a donc continué sur les 490 décisions restantes.

## 2. Exécution, erreurs, coût

| Mesure | Valeur |
| :-- | :-- |
| Décisions répondues | 500 / 500, toutes par `jev-1.14.0` |
| Appels facturés | 501 |
| Réponses rejetées | 1 sur 501 : `choice` différent de l'action la plus probable ; rejetée par notre validation puis retentée avec succès |
| Erreurs finales | 0 |
| Tokens d'entrée | 991 287 au total, 1 979 en moyenne (min 1 128, max 2 738) |
| Tokens de sortie | ~104 en moyenne, non facturés |
| **Coût constaté** | **0,0416 USD** (0,279 CNY au taux de 6,71), pour un plafond de 0,25 USD |
| Coût par appel | ≈ 0,000083 USD |
| Latence par appel (4 en parallèle) | médiane **0,51 s**, p90 **0,67 s**, max 2,5 s |
| Confiance moyenne déclarée par Jev | 0,37 |

**Écart avec l'estimation.** Le coût attendu était de 0,020 USD. Le JSON se tokenise à
~1,9 octet par token, et non 4 comme supposé : le coût réel est donc **le double** de
l'estimation, mais reste sous la borne haute (0,090 USD), qui a tenu.

## 3. Désaccords Jev ↔ CFR

**Vue d'ensemble**
- Même action principale : **57,2 %** ; même type d'action : 59,8 % ; variation totale moyenne : 0,48.
- Jev ne place en moyenne que **35 %** de sa probabilité sur l'action préférée de CFR.

**Selon la situation**

| Situation | Même action |
| :-- | --: |
| Pas de mise à payer | 68 % |
| Face à une mise | 43 % |
| Preflop | 47 % |
| Flop | 59 % |
| Turn | 62 % |
| River | 66 % |
| Contre l'hyper-agressif | 45 % |
| Contre equity | 66 % |
| Contre station | 61 % |
| Contre TAG (33 décisions) | 52 % |

**Nature des désaccords : Jev est nettement plus passif et plus prudent que CFR.**

| Action principale | CFR | Jev |
| :-- | --: | --: |
| Agressive (mise ou relance) | 140 | 14 |
| Fold | 63 | 110 |

- Dans 119 des 140 cas où CFR relance, Jev préfère check ou call.
- Dans 60 cas où CFR suit, Jev préfère se coucher, surtout preflop face à une relance.

**Exemples frappants**, sans conclusion sur qui a raison :
- river, brelan de 8 (8♦4♣ sur 2♦8♥7♦Q♣8♣) : CFR relance à 99 % ; Jev donne 34 % au fold ;
- river, quinte à l'As (Q♠J♠ sur K♠5♦A♦T♣4♦), face à une relance : CFR relance à 100 % ;
  Jev donne 27 % au fold ;
- preflop en grosse blind face à une ouverture à 300 : avec 9♣6♦, 8♠5♦ et K♥9♦, CFR défend ;
  Jev se couche à 57-58 % avec les deux premières.

## 4. Ce que cela implique

**Ce que le pilote ne dit pas.**
- Il ne dit pas si Jev joue mieux ou moins bien : un désaccord n'est pas une erreur.
- Les exemples montrent toutefois des abandons de mains très fortes que la théorie
  réprouverait, ce qui rend une amélioration générale peu probable sans filtre.

**Coût et durée révisés pour l'étape 1** du benchmark (TAG et equity, ~6 600 appels) :
- coût attendu **≈ 0,55 USD** (au lieu de 0,26), borne haute toujours 1,2 USD ;
- durée ≈ **1 h** en séquentiel à 0,5 s par appel.

**L'étape 1 n'a pas été lancée**, conformément à ta consigne.
