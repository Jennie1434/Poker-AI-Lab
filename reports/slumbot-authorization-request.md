# Demande d'autorisation — benchmark contre Slumbot

**Statut : brouillon, non envoyé.** Aucun contact n'a été pris avec slumbot.com, et aucune main
n'y a été jouée. Le client `backend/pokerbench/slumbot.py` refuse de jouer en réel sans la
référence d'une autorisation écrite (`--live-authorization`).

**Destinataire** : Eric Jackson, auteur de Slumbot. Canaux possibles : le formulaire ou l'adresse
indiqués sur slumbot.com (le site n'était pas consultable depuis l'environnement de travail), ou
une issue sur `github.com/ericgjackson/slumbot2019`, comme l'a fait un autre chercheur dans l'issue #49.

**À compléter avant envoi** : `[Nom]`, `[adresse e-mail]`, `[période]`. Le volume ci-dessous
découle du calcul de taille d'échantillon de MISSION_7A/7B (≈ 42 000 mains pour un IC à
±20 bb/100) ; ajuste-le si tu veux viser moins.

---

## Message (en anglais)

> **Subject:** Permission request: benchmarking a CFR poker bot against the Slumbot API
>
> Dear Mr. Jackson,
>
> I am [Name], and I maintain Poker AI Lab, an open-source (MIT) research project that evaluates
> heads-up no-limit hold'em agents. The game engine is PokerKit, and our reference agent is a
> tabular MCCFR policy with a small exploitative overlay driven by public statistics. All our
> evaluations so far have been against local scripted opponents, and Slumbot is the natural
> external reference. I would like to ask for your permission before running any automated games
> against the Slumbot API.
>
> What we would run, if you agree:
> - **Volume.** At most two agents, about 42,000 hands each (about 85,000 hands in total).
>   We would stop earlier if you prefer a lower cap.
> - **Pacing.**
>   - A single sequential session: one request at a time and at least 0.5 s between requests.
>   - Exponential back-off on HTTP 429/5xx.
>   - Automatic stop after three consecutive failed hands.
>   - Spread over [period]; we can restrict it to hours you prefer.
> - **Format.** Your standard game (50/100 blinds, 200 BB stacks, `new_hand` / `act`), with no
>   modification of the protocol and no attempt to probe the server beyond normal play.
> - **Data.**
>   - We keep only our own hand records.
>   - We publish aggregate results only: bb/100 with confidence intervals, method and code.
>   - We credit Slumbot and you by name, with a link to slumbot.com.
> - **Account.** Anonymous or logged in, whichever you prefer. With an account you could check our
>   reported results against yours.
>
> Could you tell us whether this is acceptable, and whether you would like a different hand cap,
> rate or schedule? We will not start without your reply, and we will stop immediately at any
> time if you ask.
>
> Thank you for keeping Slumbot available to researchers.
>
> Best regards,
> [Name] — Poker AI Lab — [email]

---

## Ce que nous nous engageons à respecter (déjà dans le code)

| Engagement | Mécanisme |
| :-- | :-- |
| Pas de jeu sans accord écrit | `Authorization(reference, max_hands)`, refusée sans référence |
| ≤ 1 requête à la fois, ≥ 0,5 s d'intervalle | `HttpTransport` (refuse un intervalle plus court) |
| Recul sur erreur, arrêt après échecs | backoff 2-4-8-16 s (plafond 300 s) ; arrêt après 3 mains en échec |
| Plafond de mains | `max_hands` de l'autorisation (≤ 100 000) |
| Comptabilité vérifiable | chaque main rejouée dans PokerKit ; gains annoncés comparés au règlement |

**Après réponse** : enregistrer la référence (date et canal du message), autoriser `slumbot.com`
dans la politique réseau de l'environnement, puis lancer
`python -m pokerbench.slumbot --live-authorization "<référence>" --hands N --output …`.
