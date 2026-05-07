#!/usr/bin/env python3
"""
parse_fanout.py — Parse les fichiers CSV Locust et génère fanout.csv
 
Cherche les fichiers nommés fanout_{PARAM}_run{RUN}_stats.csv dans le dossier out/
et produit un fichier fanout.csv structuré.

Usage:
    python parse_fanout.py
    python parse_fanout.py --outdir out  --nb-instances 1
"""

import csv
import os
import re
import argparse


def parse_locust_stats(filepath: str) -> dict | None:
    """Lit un fichier *_stats.csv Locust et retourne les stats Aggregated."""
    with open(filepath, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("Name") == "Aggregated" or row.get("Name") == "/api/timeline":
                avg = float(row.get("Average Response Time", -1))
                failures = int(row.get("Failure Count", 0))
                total = int(row.get("Request Count", 0))
                return {
                    "avg_time": round(avg),
                    "failed": failures,
                    "total_requests": total
                }
    return None


def read_instances(outdir: str, prefix: str, param: int, run: int) -> str:
    """Lit le fichier _instances.txt généré pendant le test."""
    path = os.path.join(outdir, f"{prefix}_{param}_run{run}_instances.txt")
    if os.path.exists(path):
        with open(path) as f:
            return f.read().strip() or "?"
    return "?"


def main():
    parser = argparse.ArgumentParser(description="Parse Locust CSVs into fanout.csv")
    parser.add_argument("--outdir", default="out", help="Dossier contenant les CSV Locust")
    args = parser.parse_args()

    outdir = args.outdir
    pattern = re.compile(r"fanout_(\d+)_run(\d+)_stats\.csv$")

    results = []
    for filename in os.listdir(outdir):
        match = pattern.search(filename)
        if match:
            param = int(match.group(1))
            run = int(match.group(2))
            filepath = os.path.join(outdir, filename)
            stats = parse_locust_stats(filepath)
            if stats:
                nb_instances = read_instances(outdir, "fanout", param, run)
                results.append({
                    "PARAM": param,
                    "AVG_TIME": f"{stats['avg_time']}ms",
                    "RUN": run,
                    "FAILED": stats["failed"],
                    "Nb instances": nb_instances
                })
                print(f"  {filename} -> PARAM={param}, RUN={run}, AVG={stats['avg_time']}ms, "
                      f"FAILED={stats['failed']}, INSTANCES={nb_instances}")

    # Trier par PARAM puis par RUN
    results.sort(key=lambda r: (r["PARAM"], r["RUN"]))

    csv_path = os.path.join(outdir, "fanout.csv")
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["PARAM", "AVG_TIME", "RUN", "FAILED", "Nb instances"])
        writer.writeheader()
        writer.writerows(results)

    print(f"\n✅ {csv_path} généré avec {len(results)} lignes")


if __name__ == "__main__":
    main()
