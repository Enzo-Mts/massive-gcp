#!/bin/bash
# run_conc.sh — Lance l'expérience de concurrence complète
# Usage: bash run_conc.sh

HOST="https://tp-tiny-insta-enzo-sam.ew.r.appspot.com"
LOCUSTFILE="locustfile.py"
DURATION="60s"
OUTDIR="out"
SEED_SCRIPT="$HOME/massive-gcp/seed.py"
CLEAR_SCRIPT="$HOME/massive-gcp/clear.py"

# Paramètres fixes du sujet : 1000 users, 50 posts/user, 20 follows
SEED_USERS=1000
SEED_POSTS=50000   # 1000 * 50
SEED_FOLLOWS=20

mkdir -p "$OUTDIR"

LEVELS=(1 10 20 50 100 1000)
RUNS=3

# Retourne le nombre d'instances App Engine actives
count_instances() {
    gcloud app instances list --format="value(id)" 2>/dev/null | wc -l | tr -d ' '
}

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

echo "============================================"
echo " Expérience Concurrence — TinyInsta"
echo " Niveaux: ${LEVELS[*]}"
echo " Runs par niveau: $RUNS"
echo " Durée par run: $DURATION"
echo "============================================"

# Seed unique au démarrage — les tests ne font que lire les données
#echo ""
#echo "[init] Nettoyage + seed initial..."
#python3 "$CLEAR_SCRIPT" --yes
#python3 "$SEED_SCRIPT" \
 #  --users "$SEED_USERS" \
  # --posts "$SEED_POSTS" \
   #--follows-min "$SEED_FOLLOWS" \
   #--follows-max "$SEED_FOLLOWS"
#echo "[init] Pause 15s pour que Datastore se stabilise..."
sleep 15

for level in "${LEVELS[@]}"; do
    rate=$level

    for run in $(seq 1 $RUNS); do
        echo ""
        echo ">>> PARAM=$level, RUN=$run/$RUNS (spawn_rate=$rate)"
        echo "    $(date)"

        # Tuer toutes les instances pour un test propre
        kill_all_instances
        echo "    [start] Instances actives avant le test: $(count_instances)"

        # Lancer locust en arrière-plan
        locust -f "$LOCUSTFILE" \
            --host "$HOST" \
            --headless \
            -u "$level" \
            -r "$rate" \
            --run-time "$DURATION" \
            --only-summary \
            --csv "$OUTDIR/conc_${level}_run${run}" &
        LOCUST_PID=$!

        # Surveiller les instances en temps réel pendant le test
        MAX_INSTANCES=0
        echo "    [monitoring instances...]"
        while kill -0 "$LOCUST_PID" 2>/dev/null; do
            COUNT=$(count_instances)
            echo "    [$(date +%H:%M:%S)] instances actives: $COUNT"
            if [ "$COUNT" -gt "$MAX_INSTANCES" ]; then
                MAX_INSTANCES=$COUNT
            fi
            sleep 10
        done

        wait "$LOCUST_PID"

        # Sauvegarder le max d'instances observé pour ce run
        echo "$MAX_INSTANCES" > "$OUTDIR/conc_${level}_run${run}_instances.txt"
        echo "    Max instances observées: $MAX_INSTANCES"
    done
done

echo ""
echo "============================================"
echo " Génération de conc.csv..."
echo "============================================"
python3 parse_conc.py --outdir "$OUTDIR"

echo ""
echo "============================================"
echo " Terminé ! Résultats dans $OUTDIR/"
echo "============================================"