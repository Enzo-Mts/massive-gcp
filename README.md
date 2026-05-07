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

Afin de garantir des mesures fiables, toutes les instances App Engine sont supprimées entre chaque run et chaque niveau de test via la fonction `kill_all_instances()` :

```bash
# Supprime toutes les instances App Engine et attend qu'elles soient bien down
kill_all_instances() {
    echo "    [cleanup] Suppression de toutes les instances App Engine..."
    gcloud app instances list --format="value(service,version,id)" 2>/dev/null | \
        while IFS=$'\t' read -r service version id; do
            gcloud app instances delete "$id" \
                --service="$service" \
                --version="$version" \
                --quiet 2>/dev/null || true
        done

    # Attendre que les instances descendent à 0 ou 1
    echo "    [cleanup] Attente descente à 0 ou 1 instance..."
    while true; do
        REMAINING=$(count_instances)
        echo "    [$(date +%H:%M:%S)] instances restantes: $REMAINING"
        [ "$REMAINING" -le 1 ] && break
        sleep 5
    done
    echo "    [cleanup] OK — $REMAINING instance(s) active(s), lancement du test."
}
```

Cette fonction supprime toutes les instances actives via `gcloud app instances delete`, puis boucle toutes les 5 secondes jusqu'à ce que le compteur tombe à 0 ou 1. Le nombre d'instances actives est affiché juste avant le lancement du test. Les pauses fixes entre les runs ont été supprimées — c'est le polling qui garantit l'état propre.

### Comportement des utilisateurs simulés

Chaque utilisateur Locust effectue **exactement une requête** `/api/timeline` sur un utilisateur aléatoire, puis s'arrête (`raise StopUser()`). Le run se termine automatiquement quand tous les utilisateurs ont reçu leur réponse (succès ou erreur). Le paramètre `--run-time 60s` reste configuré comme timeout de sécurité maximum.

### Impact sur les mesures : cold start et burst

Cette méthodologie a deux conséquences majeures sur les temps de réponse mesurés :

**1. Les temps incluent le cold start d'App Engine.** Puisque les instances sont tuées avant chaque run, chaque test démarre à froid. Le cold start d'App Engine (démarrage de l'instance, chargement du runtime Python, import des librairies) coûte typiquement 1 à 3 secondes. Avec un seul utilisateur, on mesure déjà ~1,5 s — ce temps est essentiellement du cold start, pas du traitement métier. Comme chaque utilisateur ne fait qu'une seule requête (`raise StopUser()`), ce coût n'est jamais amorti : il n'y a pas de phase de warm-up où les requêtes suivantes bénéficieraient d'instances déjà chaudes.

**2. Le burst instantané ne laisse pas le temps à l'autoscaler.** Tous les utilisateurs simulés lancent leur requête dès qu'ils arrivent, ce qui crée un pic soudain. L'autoscaler d'App Engine, qui prend ses décisions sur des métriques moyennées avec un délai de réaction de 30 à 60 secondes, n'a pas le temps de provisionner de nouvelles instances avant que le test soit terminé. Les résultats reflètent donc la capacité du système à encaisser un pic soudain à froid, et non sa capacité à scaler progressivement sous une charge soutenue.

On observe ces effets directement dans les données brutes : pour 1 utilisateur, le temps de 1 369 ms est quasi-intégralement du cold start. Pour 10 utilisateurs, le min est à 1 475 ms et le max à 5 722 ms — toutes les requêtes arrivent dans la même seconde et paient chacune le prix du démarrage. Pour 100 utilisateurs, le min descend à 34 ms (certaines requêtes sont servies par des instances déjà chaudes) tandis que le max atteint 10 s — la variance énorme reflète le mélange entre requêtes à froid et à chaud.

**Pour un benchmark mesurant la latence stable**, il faudrait : (1) une phase de warm-up de 30–60 s avant la mesure, (2) des utilisateurs en boucle continue pendant toute la durée du run, et (3) ne pas tuer les instances entre les runs. Notre protocole mesure plutôt un **scénario de scale-up à froid**, ce qui est un test valide mais différent — et qui explique les temps systématiquement élevés.

### Format des résultats

Les fichiers CSV contiennent les colonnes : `PARAM, AVG_TIME, RUN, FAILED, Nb instances`. La colonne `FAILED` indique le nombre réel d'erreurs retournées par Locust (et non un simple indicateur binaire).

---

## Expérience 1 — Passage à l'échelle sur la charge (concurrence)

**Paramètres fixes** : 1000 utilisateurs en base, 50 posts/utilisateur, 20 followees/utilisateur.
**Variable** : nombre d'utilisateurs simultanés (1, 10, 20, 50, 100, 1000).
Chaque niveau est répété 3 fois. **Chaque utilisateur simulé effectue exactement une requête timeline**, comme demandé dans la consigne — le temps mesuré correspond donc au temps moyen pour servir une unique requête timeline par utilisateur, sous différentes charges concurrentes, **cold start inclus**.

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

Avec 1 utilisateur, la requête timeline est servie en environ **1,5 seconde** sans aucune erreur, sur une seule instance. Ce temps est essentiellement du cold start App Engine (démarrage de l'instance + chargement du runtime), et constitue notre baseline pour ce scénario à froid.

Dès 10 utilisateurs simultanés, le temps moyen bondit à **~4,6 secondes** alors que l'autoscaler n'a pas encore réagi (toujours 1 seule instance). Toutes les requêtes arrivent dans la même seconde et paient chacune le coût du cold start — les temps vont de ~1 500 ms (premier servi) à ~5 700 ms (dernier dans la file). Quelques erreurs sporadiques apparaissent (run 1 : 4 erreurs), signe que la capacité de l'instance est déjà sous tension.

À 20 utilisateurs, l'autoscaler commence à démarrer une seconde instance sur certains runs, et le temps moyen redescend légèrement à **~3,5 secondes**. Cependant la variance est importante entre les runs (2 787 ms vs 4 570 ms), ce qui reflète le caractère non-déterministe du moment où la seconde instance devient disponible.

À 50 utilisateurs, on observe 3 à 4 instances actives et un temps moyen remonté à **~5 secondes**. Les erreurs augmentent nettement (5 à 10 par run). L'autoscaler scale, mais pas assez vite pour absorber le burst initial de 50 requêtes simultanées à froid.

Le palier à **100 utilisateurs** présente un résultat contre-intuitif : avec 4 instances stables, le temps moyen retombe à **~2,9 secondes** — mieux que pour 20 et 50 utilisateurs. Les données brutes montrent un min à 34 ms (certaines requêtes servies par des instances déjà chaudes) contre un max à 10 s. Cela illustre le caractère non-déterministe du démarrage des instances : dans ce cas, les 4 instances étaient probablement disponibles plus rapidement, et une partie des requêtes a pu être servie à chaud, tirant la moyenne vers le bas.

À **1 000 utilisateurs**, l'autoscaler déploie jusqu'à 11 instances. Le temps moyen se stabilise autour de **5,7 secondes** avec une variance faible entre les runs (5 643 à 5 874 ms). Les erreurs montent à 13–14 par run, soit environ 1,3 % du total.

**En résumé** : ces résultats mesurent un scénario de **scale-up à froid** — les temps incluent le cold start d'App Engine et le burst ne laisse pas le temps à l'autoscaler de réagir pleinement. Cela explique à la fois les temps élevés (même pour 1 user : 1,5 s de cold start), le nombre d'erreurs, et les résultats non-monotones (100 users plus rapide que 50 users selon la chance au démarrage des instances). Malgré ces conditions défavorables, le système passe de 1,5 s (1 user) à 5,7 s (1 000 users), soit un facteur ~4× pour une charge multipliée par 1 000× — ce qui montre que l'autoscaler parvient tout de même à absorber une partie significative de la montée en charge.

---

## Expérience 2 — Passage à l'échelle sur la taille des données (fan-out)

**Paramètres fixes** : 1000 utilisateurs en base, 100 posts/utilisateur, 50 utilisateurs simultanés.
**Variable** : nombre de followees par utilisateur (20, 40, 60).
Chaque niveau est répété 3 fois. Le nombre d'instances n'est pas fixé — il est laissé libre à l'autoscaler.

| Followees | Temps moyen (ms) | Erreurs moyennes | Instances |
|:-:|:-:|:-:|:-:|
| 20 | 3 077 | 7.3 | 4 |
| 40 | 6 976 | 6.3 | 4 |
| 60 | 10 124 | 6.3 | 4 |

![Fanout](fanout.png)

### Interprétation

Bien que le nombre d'instances ne soit pas fixé, l'autoscaler a provisionné systématiquement 4 instances sur tous les runs. La charge concurrente étant constante (50 utilisateurs), cela permet d'isoler l'impact du fan-out sur les performances. Les temps incluent également le cold start, mais celui-ci est constant entre les niveaux — la progression observée est donc bien attribuable au fan-out.

Avec 20 followees, le temps moyen est de **~3 secondes**. Avec 40 followees, il double à **~7 secondes**. Avec 60 followees, il atteint **~10 secondes**. La relation est quasi-linéaire : chaque tranche de 20 followees supplémentaires ajoute environ 3,5 secondes au temps de réponse. C'est cohérent avec l'architecture de la timeline qui doit récupérer les posts de chaque followee individuellement — doubler le nombre de followees double mécaniquement le travail à effectuer.

La variance entre les runs est plus marquée à 60 followees, avec un écart entre le run le plus lent (12 150 ms) et le plus rapide (8 313 ms). Le nombre d'erreurs reste stable autour de 6–7 par run quel que soit le fan-out, ce qui confirme que les erreurs sont davantage liées à la charge concurrente (50 utilisateurs simultanés en burst) qu'à la taille des données à récupérer.

**En résumé** : le temps de réponse croît linéairement avec le nombre de followees. La requête timeline ne bénéficie d'aucune optimisation type batch ou cache — elle scale en O(n) avec le fan-out.

---

## Conclusion — Est-ce que ça scale ?

**Oui, mais nos mesures surestiment les temps de réponse réels.**

Notre protocole de test mesure un **scénario de scale-up à froid** : les instances sont tuées avant chaque run, chaque utilisateur ne fait qu'une seule requête (pas d'amortissement du cold start), et le burst instantané ne laisse pas le temps à l'autoscaler de réagir. Les temps mesurés incluent donc systématiquement le cold start d'App Engine (1–3 s), ce qui gonfle artificiellement les résultats. Pour mesurer la latence stable du système, il faudrait une phase de warm-up, des requêtes en boucle continue, et ne pas tuer les instances entre les runs.

Malgré cela, les tendances observées restent significatives :

Sur l'axe de la **concurrence**, App Engine parvient à contenir la dégradation même dans ces conditions défavorables : le temps de réponse ne croît que d'un facteur ~4× quand la charge est multipliée par 1 000×, grâce à l'ajout progressif d'instances. Sous une charge soutenue avec des instances chaudes, les performances seraient vraisemblablement bien meilleures.

Sur l'axe du **fan-out**, la requête timeline scale en O(n) — ce qui est attendu pour une architecture sans dénormalisation. Le cold start étant constant entre les niveaux, la progression linéaire observée (+3,5 s par tranche de 20 followees) reflète fidèlement le coût du fan-out. C'est le point faible principal : avec 60 followees la timeline met déjà 10 secondes à se construire. Pour aller au-delà, il faudrait implémenter des optimisations côté données (dénormalisation de la timeline, cache, requêtes batch sur le Datastore).
