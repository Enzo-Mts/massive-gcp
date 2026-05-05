# TinyInsta — Does it Scale?

## Objectif

Ce projet évalue le passage à l'échelle de **TinyInsta**, un réseau social minimaliste déployé sur Google App Engine. Deux expériences de benchmark ont été menées avec [Locust](https://locust.io/) pour mesurer le temps moyen d'une requête `/api/timeline` :

1. **Concurrence** — nombre d'utilisateurs simultanés croissant (données fixes)
2. **Fan-out** — nombre de followees croissant (concurrence fixe)

## Webapp

🔗 **URL de l'application déployée** : _https://tp-tiny-insta-enzo-sam.ew.r.appspot.com_

---

## Méthodologie

### Isolation entre les runs

Afin de garantir des mesures fiables, une fonction `kill_all_instances()` est appelée au début de chaque run. Elle supprime toutes les instances App Engine actives via `gcloud app instances delete`, puis boucle toutes les 5 secondes jusqu'à ce que le compteur d'instances tombe à 0 ou 1. Le nombre d'instances actives est affiché juste avant le lancement du test. Les pauses fixes entre les runs ont été supprimées — c'est le polling qui garantit l'état propre.

### Comportement des utilisateurs simulés

Chaque utilisateur Locust effectue **exactement une requête** `/api/timeline` sur un utilisateur aléatoire, puis s'arrête (`raise StopUser()`). Le run se termine automatiquement quand tous les utilisateurs ont reçu leur réponse (succès ou erreur). Le paramètre `--run-time 60s` reste configuré comme timeout de sécurité maximum.

### Format des résultats

Les fichiers CSV contiennent les colonnes : `PARAM, AVG_TIME, RUN, FAILED, Nb instances`. La colonne `FAILED` indique le nombre réel d'erreurs retournées par Locust (et non un simple indicateur binaire).

---

## Expérience 1 — Passage à l'échelle sur la charge (concurrence)

**Paramètres fixes** : 1000 utilisateurs en base, 50 posts/utilisateur, 20 followees/utilisateur.
**Variable** : nombre d'utilisateurs simultanés (1, 10, 20, 50, 100, 1000).
Chaque niveau est répété 3 fois. **Chaque utilisateur simulé effectue exactement une requête timeline**, comme demandé dans la consigne — le temps mesuré correspond donc au temps moyen pour servir une unique requête timeline par utilisateur, sous différentes charges concurrentes.

| Utilisateurs simultanés | Temps moyen (ms) | Erreurs moyennes | Instances |
|:-:|:-:|:-:|:-:|
| 1 | 1 492 | 0 | 1 |
| 10 | 4 646 | 1.7 | 1 |
| 20 | 3 538 | 3.3 | 1–2 |
| 50 | 5 069 | 8 | 3–4 |
| 100 | 2 914 | 7 | 4 |
| 1 000 | 5 755 | 13.3 | 9–11 |

![Concurrence](conc.png)

### Interprétation

Avec 1 utilisateur, la requête timeline est servie en environ **1,5 seconde** sans aucune erreur, sur une seule instance — c'est notre baseline.

Dès 10 utilisateurs simultanés, le temps moyen bondit à **~4,6 secondes** alors que l'autoscaler n'a pas encore réagi (toujours 1 seule instance). L'instance unique absorbe la charge, mais au prix d'une latence multipliée par 3. Quelques erreurs sporadiques apparaissent (run 1 : 4 erreurs), signe que la capacité de l'instance est déjà sous tension.

À 20 utilisateurs, l'autoscaler commence à démarrer une seconde instance sur certains runs, et le temps moyen redescend légèrement à **~3,5 secondes**. Cependant la variance est importante entre les runs (2 787 ms vs 4 570 ms), ce qui reflète le caractère non-déterministe du moment où la seconde instance devient disponible.

À 50 utilisateurs, on observe 3 à 4 instances actives et un temps moyen remonté à **~5 secondes**. Les erreurs augmentent nettement (5 à 10 par run). L'autoscaler scale, mais pas assez vite pour absorber le burst initial de 50 requêtes simultanées.

Le palier à **100 utilisateurs** est intéressant : avec 4 instances stables, le temps moyen retombe à **~2,9 secondes** — mieux que pour 50 utilisateurs. L'explication probable est que l'infrastructure dispose déjà de 4 instances actives (héritées du nettoyage précédent ou démarrées rapidement), ce qui permet de distribuer la charge efficacement. Les erreurs restent contenues autour de 7.

À **1 000 utilisateurs**, l'autoscaler déploie jusqu'à 11 instances. Le temps moyen se stabilise autour de **5,7 secondes** avec une variance faible entre les runs (5 643 à 5 874 ms), ce qui montre que le système atteint un régime stable. Les erreurs montent à 13–14 par run, soit environ 1,3 % du total — un taux acceptable sous cette charge extrême.

**En résumé** : le temps de réponse ne croît pas linéairement avec le nombre d'utilisateurs. On passe de 1,5 s (1 user) à 5,7 s (1 000 users), soit un facteur ~4× pour une charge multipliée par 1 000×. L'autoscaler d'App Engine fait son travail en ajoutant des instances, mais avec un temps de réaction qui introduit de la variance et des erreurs transitoires, surtout sur les petites charges (10–50 users) où le scaling n'est pas encore enclenché.

---

## Expérience 2 — Passage à l'échelle sur la taille des données (fan-out)

**Paramètres fixes** : 1000 utilisateurs en base, 100 posts/utilisateur, 50 utilisateurs simultanés.
**Variable** : nombre de followees par utilisateur (20, 40, 60).
Chaque niveau est répété 3 fois. Le nombre d'instances est stable à 4 sur tous les runs.

| Followees | Temps moyen (ms) | Erreurs moyennes | Instances |
|:-:|:-:|:-:|:-:|
| 20 | 3 077 | 7.3 | 4 |
| 40 | 6 976 | 6.3 | 4 |
| 60 | 10 124 | 6.3 | 4 |

![Fanout](fanout.png)

### Interprétation

L'infrastructure est ici constante (4 instances sur tous les runs), ce qui permet d'isoler l'impact du fan-out sur les performances.

Avec 20 followees, le temps moyen est de **~3 secondes**. Avec 40 followees, il double à **~7 secondes**. Avec 60 followees, il atteint **~10 secondes**. La relation est quasi-linéaire : chaque tranche de 20 followees supplémentaires ajoute environ 3,5 secondes au temps de réponse. C'est cohérent avec l'architecture de la timeline qui doit récupérer les posts de chaque followee individuellement — doubler le nombre de followees double mécaniquement le travail à effectuer.

La variance entre les runs diminue avec le fan-out : à 60 followees, l'écart entre le run le plus lent (12 150 ms) et le plus rapide (8 313 ms) est plus important en valeur absolue mais reste dans un rapport similaire. Le nombre d'erreurs reste stable autour de 6–7 par run quel que soit le fan-out, ce qui confirme que les erreurs sont davantage liées à la charge concurrente (50 utilisateurs simultanés) qu'à la taille des données à récupérer.

**En résumé** : le temps de réponse croît linéairement avec le nombre de followees. La requête timeline ne bénéficie d'aucune optimisation type batch ou cache — elle scale en O(n) avec le fan-out.

---

## Conclusion — Est-ce que ça scale ?

**Oui, mais avec des nuances.**

Sur l'axe de la **concurrence**, App Engine scale correctement grâce à l'autoscaler : le temps de réponse ne croît que d'un facteur ~4× quand la charge est multipliée par 1 000×. Le système absorbe la montée en charge en ajoutant des instances, ce qui maintient une latence raisonnable. Les principales limites sont le délai de réaction de l'autoscaler (qui cause des erreurs transitoires sur les bursts) et le cold start des nouvelles instances.

Sur l'axe du **fan-out**, la requête timeline scale en O(n) — ce qui est attendu pour une architecture sans dénormalisation. C'est le point faible principal : avec 60 followees la timeline met déjà 10 secondes à se construire. Pour aller au-delà, il faudrait implémenter des optimisations côté données (dénormalisation de la timeline, cache, requêtes batch sur le Datastore).
