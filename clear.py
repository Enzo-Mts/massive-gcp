#!/usr/bin/env python3
"""Supprime toutes les entités User et Post du Datastore.

Usage:
  python clear.py                  # supprime User + Post
  python clear.py --kind Post      # supprime uniquement les posts
  python clear.py --dry-run        # affiche ce qui serait supprimé sans écrire
  python clear.py --yes            # ne demande pas de confirmation
"""
from __future__ import annotations
import argparse
from google.cloud import datastore

BATCH_SIZE = 100  # limite Datastore par commit
TIMEOUT = 30      # secondes avant d'abandonner


def delete_kind(client: datastore.Client, kind: str, dry: bool) -> int:
    total = 0
    print(f"  {kind}: suppression en cours...")

    while True:
        query = client.query(kind=kind)
        query.keys_only()

        try:
            keys = [e.key for e in query.fetch(limit=BATCH_SIZE, timeout=TIMEOUT)]
        except Exception as e:
            print(f"  {kind}: erreur — {e}")
            break

        if not keys:
            break

        total += len(keys)
        if not dry:
            client.delete_multi(keys)
        print(f"    {'[dry] trouverait' if dry else 'supprimé'} {total} entité(s)...")

    if total == 0:
        print(f"  {kind}: aucune entité trouvée.")
    return total


def main():
    parser = argparse.ArgumentParser(description="Nettoie le Datastore TinyInsta")
    parser.add_argument("--kind", choices=["User", "Post"], default=None,
                        help="Supprimer uniquement ce kind (défaut: les deux)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Affiche ce qui serait supprimé sans rien écrire")
    parser.add_argument("--yes", action="store_true",
                        help="Ne demande pas de confirmation")
    args = parser.parse_args()

    kinds = [args.kind] if args.kind else ["Post", "User"]

    if args.dry_run:
        print("[Dry-Run] Aucune suppression ne sera effectuée.\n")
    elif not args.yes:
        print(f"Vous allez supprimer TOUTES les entités : {', '.join(kinds)}")
        confirm = input("Confirmer ? (oui/N) : ").strip().lower()
        if confirm != "oui":
            print("Annulé.")
            return

    client = datastore.Client()
    total = 0
    for kind in kinds:
        total += delete_kind(client, kind, args.dry_run)

    action = "auraient été supprimées" if args.dry_run else "supprimées"
    print(f"\n[Clear] {total} entité(s) {action}.")


if __name__ == "__main__":
    main()
