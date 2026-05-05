#!/bin/bash
# run_fanout.sh — Lance l'expérience fanout complète
# Seed + benchmark pour chaque niveau de followees
# Génère automatiquement fanout.csv à la fin
#
# Usage: bash run_fanout.sh

HOST="https://tp-tiny-insta-enzo-sam.ew.r.appspot.com"
LOCUSTFILE="locustfile.py"
DURATION="60s"
OUTDIR="out"
SEED_SCRIPT="$HOME/massive-gcp/seed.py"
CLEAR_SCRIPT="$HOME/massive-gcp/clear.py"

# Paramètres fixes
USERS=1000
POSTS_TOTAL=100000   # 1000 users * 100 posts/user
CONCURRENT=50
SPAWN_RATE=50

# Variable : nombre de followees
FOLLOW_LEVELS=(20 40 60)
RUNS=3

mkdir -p "$OUTDIR"

seed_for_follows() {
    local follows=$1
    echo "  [seed] Nettoyage + seed: $USERS users, $POSTS_TOTAL posts, $follows follows..."
    python3 "$CLEAR_SCRIPT" --yes
    python3 "$SEED_SCRIPT" \
        --users "$USERS" \
        --posts "$POSTS_TOTAL" \
        --follows-min "$follows" \
        --follows-max "$follows" \
        --prefix user
    echo "  [seed] Pause 20s pour que Datastore se stabilise..."
    sleep 20
}

echo "--- Instances au démarrage ---"
gcloud app instances list 2>/dev/null
echo ""

echo "============================================"
echo " Expérience Fanout — TinyInsta"
echo " Users: $USERS, Posts total: $POSTS_TOTAL"
echo " Concurrent users: $CONCURRENT"
echo " Follow levels: ${FOLLOW_LEVELS[*]}"
echo " Runs par niveau: $RUNS"
echo " Durée par run: $DURATION"
echo "============================================"

for follows in "${FOLLOW_LEVELS[@]}"; do
    echo ""
    echo "########################################"
    echo "# FOLLOWS=$follows"
    echo "########################################"

    # Seed une seule fois par niveau — les 3 runs lisent les mêmes données
    seed_for_follows "$follows"

    for run in $(seq 1 $RUNS); do
        echo ""
        echo ">>> FOLLOWS=$follows, RUN=$run/$RUNS"
        echo "    $(date)"

        # Lancer locust en arrière-plan
        locust -f "$LOCUSTFILE" \
            --host "$HOST" \
            --headless \
            -u "$CONCURRENT" \
            -r "$SPAWN_RATE" \
            --run-time "$DURATION" \
            --only-summary \
            --csv "$OUTDIR/fanout_${follows}_run${run}" &
        LOCUST_PID=$!

        # Surveiller les instances en temps réel pendant le test
        MAX_INSTANCES=0
        echo "    [monitoring instances...]"
        while kill -0 "$LOCUST_PID" 2>/dev/null; do
            COUNT=$(gcloud app instances list --format="value(id)" 2>/dev/null | wc -l | tr -d ' ')
            echo "    [$(date +%H:%M:%S)] instances actives: $COUNT"
            if [ "$COUNT" -gt "$MAX_INSTANCES" ]; then
                MAX_INSTANCES=$COUNT
            fi
            sleep 10
        done

        wait "$LOCUST_PID"

        # Sauvegarder le max d'instances observé pour ce run
        echo "$MAX_INSTANCES" > "$OUTDIR/fanout_${follows}_run${run}_instances.txt"
        echo "    Max instances observées: $MAX_INSTANCES"
        echo "    Pause 10s..."
        sleep 10
    done
done

echo ""
echo "============================================"
echo " Génération de fanout.csv..."
echo "============================================"
python3 parse_fanout.py --outdir "$OUTDIR"

echo ""
echo "============================================"
echo " Terminé ! Résultats dans $OUTDIR/fanout.csv"
echo "============================================"