#!/usr/bin/env python3
"""
plot_results.py — Génère les barplots conc.png et fanout.png
à partir des fichiers CSV dans out/.

Usage:
    python plot_results.py
"""

import csv
import os
import numpy as np
import matplotlib.pyplot as plt


OUT_DIR = "out"


def parse_csv(filepath: str) -> list[dict]:
    """Lit un CSV et retourne une liste de dicts."""
    rows = []
    with open(filepath, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


def parse_time(time_str: str) -> float:
    """Convertit '123ms' en float (en secondes)."""
    time_str = time_str.strip().lower()
    if time_str.endswith("ms"):
        return float(time_str.replace("ms", "")) / 1000.0
    return float(time_str)


def make_barplot(csv_path: str, output_path: str, xlabel: str, title: str):
    """
    Crée un barplot avec barres d'erreur (variance sur 3 runs)
    à partir d'un CSV avec colonnes PARAM, AVG_TIME, RUN, FAILED.
    """
    rows = parse_csv(csv_path)

    # Grouper par PARAM
    data = {}
    for row in rows:
        param = int(row["PARAM"])
        time_s = parse_time(row["AVG_TIME"])
        if param not in data:
            data[param] = []
        data[param].append(time_s)

    params = sorted(data.keys())
    means = [np.mean(data[p]) for p in params]
    stds = [np.std(data[p]) for p in params]

    # Créer le barplot
    fig, ax = plt.subplots(figsize=(10, 6))

    x = np.arange(len(params))
    bars = ax.bar(x, means, yerr=stds, capsize=8, color="#4A90D9",
                  edgecolor="black", linewidth=0.8, alpha=0.85)

    ax.set_xlabel(xlabel, fontsize=13)
    ax.set_ylabel("Temps moyen par requête (s)", fontsize=13)
    ax.set_title(title, fontsize=15, fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels([str(p) for p in params], fontsize=12)
    ax.tick_params(axis='y', labelsize=11)

    # Ajouter les valeurs sur les barres
    for i, (m, s) in enumerate(zip(means, stds)):
        if m < 1.0:
            label = f"{m*1000:.0f}ms"
        else:
            label = f"{m:.2f}s"
        ax.text(i, m + s + 0.02 * max(means), label,
                ha='center', va='bottom', fontsize=10, fontweight='bold')

    ax.set_ylim(bottom=0)
    ax.grid(axis='y', alpha=0.3)
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()

    print(f"✅ Graphique sauvegardé: {output_path}")


def main():
    conc_csv = os.path.join(OUT_DIR, "conc.csv")
    fanout_csv = os.path.join(OUT_DIR, "fanout.csv")

    if os.path.exists(conc_csv):
        make_barplot(
            conc_csv,
            os.path.join(OUT_DIR, "conc.png"),
            xlabel="Nombre d'utilisateurs concurrents",
            title="Temps moyen par requête selon la concurrence"
        )
    else:
        print(f"⚠ {conc_csv} non trouvé — lance d'abord benchmark.py conc")

    if os.path.exists(fanout_csv):
        make_barplot(
            fanout_csv,
            os.path.join(OUT_DIR, "fanout.png"),
            xlabel="Nombre de followees par utilisateur",
            title="Temps moyen par requête selon le fanout"
        )
    else:
        print(f"⚠ {fanout_csv} non trouvé — lance d'abord benchmark.py fanout")


if __name__ == "__main__":
    main()
