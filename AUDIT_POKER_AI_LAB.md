# Poker AI Lab — audit et premier incrément

Ce document conserve l'état du premier incrément. La mission 2 (benchmark,
rake, agent à estimation d'équité et tableau de bord) est décrite dans
[BENCHMARK_LAB.md](BENCHMARK_LAB.md), avec ses résultats et commandes.

Audit du 25 octobre 2026. Base locale : fork `Jennie1434/Poker-AI-Lab`,
issu de JevPokerBench de ProphetLab. La licence MIT et la notice de copyright
ProphetLab sont conservées. Les API, adaptateurs et poids de modèles conservent
leurs propres conditions. Aucun service de poker tiers n'est intégré.

## Lecture et architecture avant modification

Documents lus : `README.md`, `BENCHMARK.md`, `SECURITY.md`, `MODEL_AUDIT.md`,
`TEST_REPORT.md`, ainsi que `LICENSE` et les manifestes de dépendances.

| Composant | Responsabilité et constat |
| --- | --- |
| `engine.py` / PokerKit 0.7.6 | Distribution déterministe côté serveur, blinds, actions légales, all-in, pots annexes et règlement. `Hand.apply` valide l'action. Les tailles proposées constituent une discrétisation des mises no-limit, pas toutes les mises possibles. |
| `Hand.observation` | Alias de sièges, cartes du seul acteur et cartes publiques, historique sans distributions adverses ; pas de graine ni de paquet. Les enregistrements internes complets ne sont pas des observations d'agent. |
| `runner.py` | Orchestration asynchrone, reprise, cache des décisions, bankroll/réserves, cash et SNG. Un échec fournisseur suspend un benchmark ; une salle humaine utilise check/fold pour continuer. Ces deux résultats ne doivent pas être mélangés. |
| `provider.py`, `official_adapter.py` | Routage, budgets, capacités, validation et reprises. Jev utilise actuellement le protocole natif `/v1/systemone` via HTTP ; DeepSeek et les routes compatibles passent par le System One Adapter officiel. Ne pas appeler le chemin Jev actuel un nouvel adaptateur SDK validé. |
| FastAPI, `store.py`, `accounts.py` | API et persistance SQLite, comptes, autorisations, décisions et parties. Un seul processus backend est préconisé. |
| `rooms.py`, `public_access.py` | Salles humaines privées existantes, contrôle du propriétaire et filtrage des vues/replays. Les actions humaines sont revalidées côté serveur avec numéro de main et compteur d'actions. |
| React / Vite | Interface, salles, replay, advisor, traductions et sons. Le backend sert le bundle ; Vite relaie `/api` et `/v1` vers le backend en développement. |
| Reporting / benchmark | Cash et SNG séparés ; ajustement de chance après all-in, distinct de l'EV stratégique. Pas de rake. Le parcours actuel ne constitue pas encore le benchmark heads-up demandé avec positions équilibrées et intervalle de confiance. |

Les tests existants couvrent notamment les pots annexes, relances non rouvertes,
conservation des jetons, replays, limites de visibilité, propriété des salles,
clés personnelles et destinations réseau. Cet audit et ces tests ne constituent
pas une certification de sécurité ni une vérification des modèles hébergés.

## Première amélioration livrée

`backend/pokerbench/agents.py` introduit le contrat asynchrone
`Agent.choose_action(observation) -> action_id` et deux implémentations locales :

- `RandomAgent` : uniforme sur les actions proposées, avec RNG indépendant du
  paquet. Cela n'est pas uniforme sur toutes les mises possibles.
- `HeuristicAgent` : check gratuit, call si son coût ne dépasse pas un tiers du
  pot courant, sinon fold. Cette référence volontairement faible n'estime pas
  l'équité, ignore la force des cartes et ne relance jamais.

`play_action` transmet une copie profonde de l'observation filtrée. Un agent
ne reçoit ni `Hand`, ni paquet, ni graine de distribution. Le serveur rejette
les décisions illégales ou devenues obsolètes avant `Hand.apply`. La copie
protège aussi les listes de cartes contre les mutations d'un plugin.
Il s'agit de plugins Python de confiance, pas d'une isolation de code hostile.
L'appelant doit sérialiser l'accès à la main pendant une décision.

`local_play.py` exécute des mains heads-up réelles avec PokerKit, alternance du
bouton, stacks réinitialisés à 200 BB par main, blinds 50/100, unité de 50 jetons,
sans rake. Il vérifie la conservation des jetons. Exemple :

```bash
cd /workspace/Poker-AI-Lab
.venv/bin/python -m pokerbench.local_play --hands 100 --deck-seed 1234 --policy-seed 5678
```

Résultat observé : 100 mains, 331 décisions, +12 200 jetons pour l'agent aléatoire
et −12 200 pour l'heuristique. C'est un contrôle d'intégration, **pas une mesure
de force statistiquement validée**. Les graines et les versions doivent rester
fixes pour le reproduire. Aucun historique privé n'est exporté par cette commande.

Le moteur, les règles, l'API et l'interface existante n'ont pas été modifiés.
Les nouveaux agents ne sont pas encore sélectionnables dans les salles web.

## Suite prévue et limites méthodologiques

1. **Agents Jev et entraînables.** Implémenter le même contrat en conservant
   l'adaptateur officiel applicable, la validation des probabilités, les budgets,
   l'identité du modèle et les règles de confidentialité. Vérifier le contrat
   natif Jev et le SDK officiel avant ce branchement ; pas de substitution
   silencieuse. Séparer entraînement et inférence, figer les checkpoints et les
   RNG pendant l'évaluation.
2. **CFR heads-up.** D'abord valider regret matching et stratégie moyenne sur
   un petit jeu à solution connue (Kuhn comme test algorithmique uniquement).
   Définir ensuite une abstraction heads-up Hold'em avec profondeur fixe,
   ensemble fini de mises et regroupements de mains, en conservant historique
   public et rappel des observations/actions propres dans les ensembles
   d'information. PokerKit reste l'autorité de transition et de paiement.
   Documenter précisément le mapping cartes/actions et mesurer l'erreur
   d'abstraction. Une convergence dans le jeu abstrait ne prouve ni convergence
   ni faible exploitabilité dans le no-limit complet ; ne pas annoncer une
   stratégie GTO du Hold'em. Aucun CFR ou self-play entraînable n'est livré ici.
3. **Benchmark dédié.** Au moins 10 000 mains terminées, exactement 5 000 par
   position pour chaque politique, stacks et règles fixés. Manifeste avec commit,
   versions, paramètres, graines séparées, checkpoint et nombre réellement
   terminé ; échecs explicites plutôt que mains remplacées silencieusement.
   Rapporter `100 * somme(profits en BB) / nombre de mains`, et IC à 95 %.
   Pour des donnes dupliquées avec échange des positions, bootstrap par paire
   indépendante, jamais par décision ; enregistrer la méthode et sa graine.
   Conserver un journal local de chaque observation autorisée et décision,
   version de politique et résultat, sans clé ni carte adverse cachée ; séparer
   les traces d'arbitre et ne jamais les transmettre aux agents ou à une salle.
   Les 100 mains de smoke ne satisfont pas ce jalon de 10 000 mains.
4. **Rake.** Évaluer d'abord le cas zéro puis des scénarios explicitement définis
   (pourcentage, plafond, no-flop-no-drop, arrondi). Calculer les prélèvements sur
   les pots éligibles au règlement, vérifier `somme des profits = -rake`, et
   distinguer score brut/net. Une simple soustraction moyenne après coup ne
   simule pas l'effet du rake sur les décisions. Le rake rend aussi le jeu à
   somme non constante : les garanties du CFR classique à deux joueurs et
   somme nulle ne se transposent pas automatiquement.
5. **Salle humain contre IA locale.** Réutiliser comptes, propriété, jetons
   fictifs et vues filtrées existants ; brancher les agents locaux dans le runner
   derrière une configuration serveur explicite. Ajouter les tests API de bout
   en bout (création, tour humain, refus d'action périmée, autre compte, replay
   et stream), sans exposition de cartes adverses ni prise de décision côté client.

Aucune automatisation ou assistance en temps réel à une plateforme de poker
tierce n'est prévue sans autorisation explicite de son opérateur.

## Mise en route, commandes et vérification

Environnement Python 3.12.14 / Node 24.19.0 ; dépendances Python du manifeste,
frontend installé avec `npm ci` et son lockfile. `.env` et le registre local
restent ignorés par Git ; aucune clé n'a été imprimée ou ajoutée. Pas de blocage
de configuration constaté. Le serveur local déjà démarré a été réutilisé.

Commandes exécutées depuis la racine, sauf mention contraire :

```bash
# Script d'installation de l'environnement, déjà créé durant l'onboarding :
bash /workspace/poker-cloud-install.sh
# Il réexécute pip install -e '.[test]', pip check, npm ci et npm run build,
# et conserve .env/config existants.
.venv/bin/python -m pytest -q
# Depuis frontend :
npm test
# Démarrage effectué durant l'onboarding, processus réutilisé et vérifié :
# depuis la racine
.venv/bin/uvicorn pokerbench.api:app --host 127.0.0.1 --port 8097
curl --fail --silent http://127.0.0.1:8097/api/health
# Nouveaux contrôles, depuis la racine :
.venv/bin/python -m pytest -q backend/tests/test_agents.py
.venv/bin/python -m pokerbench.local_play --hands 100
.venv/bin/python -m pytest -q
# Depuis frontend, navigateur système disponible :
PB_BASE_URL=http://127.0.0.1:8097 PB_BROWSER_EXECUTABLE=/usr/bin/chromium npm run test:browser
```

Résultats avant modification : 589 tests Python réussis, 26 tests frontend
réussis, compilation TypeScript/Vite réussie, health HTTP valide.
Les 13 nouveaux tests passent : confidentialité et copie défensive, décisions
illégales sans mutation, refus d'une décision obsolète, fin de main, seuil de
l'heuristique, reproductibilité et couverture des choix aléatoires, parties
réelles complètes et conservation, rejet d'une exécution vide.

Résultats après modification : **602 tests Python réussis en 18,82 s**,
aucun échec ; tests navigateur réussis (desktop/mobile, anglais/chinois,
isolation de session et parcours avec API simulée). Le health HTTP est toujours
valide. `git diff --check` ne signale aucune erreur ; les seuls nouveaux fichiers
sont ce rapport, `agents.py`, `local_play.py` et `test_agents.py`.

Limites : aucun appel réel aux fournisseurs, aucune validation de clés, aucun
entraînement, aucun benchmark statistique de 10 000 mains ni rake implémenté.
Les appels modèles ne sont pas nécessaires à cette première amélioration.

## Mission 3 (terminée)

Commencée dans Codex, terminée dans Claude Code après récupération de la branche
`codex/missions-1-3`. Les 92 000 mains du plan ont été rejouées à l'identique (11
`hands.csv` et 22 empreintes SHA-256 identiques), puis analysées : agrégation des 3 graines,
rake 0/2/5/7 % (plafond 3 BB), sensibilité 64/256/1024 tirages et fréquences. Résultat
principal : EquityHeuristicAgent perd −187,83 bb/100 nets [−209,55 ; −166,11] contre
TightAggressiveAgent. **643 tests Python et 26 tests frontend réussis.** Détails, commandes et
limites : `MISSION_3.md`. Aucun CFR/self-play lancé.

## Mission 4 (terminée)

CFR, CFR+ et MCCFR validés sur Kuhn (exploitabilité 0,00001, valeur −1/18) et Leduc
(0,00026, valeur −0,0856). Abstraction heads-up Hold'em vérifiée jeton par jeton contre
PokerKit ; `CFRAgent` gelé intégré au benchmark (`--agent-a cfr --cfr-policy`). Après
200 000 itérations de self-play, et sur 30 000 mains par adversaire avec des graines
nouvelles (rake 5 %), il bat Random (+565,7 bb/100), Heuristic (+52,1) et Equity (+172,1).
Contre TightAggressive, le résultat est non concluant : −9,6 [−27,3 ; +8,1]. **668 tests
Python et 26 tests frontend réussis.** Détails : `MISSION_4.md`.
