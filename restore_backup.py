"""Restaure les donnees entrainees (coups de bras / mouvements + commentaires)
depuis un fichier JSON de sauvegarde (celui recu par email via /api/backup).

Usage :
    python restore_backup.py chemin/vers/pdc_swim_backup.json

N'ecrase jamais toute la base : chaque ligne du fichier est reinjectee par
upsert (cle course/longueur), les lignes deja identiques ne changent rien,
les lignes modifiees depuis la sauvegarde sont ecrasees par la version du
fichier - donc pense a restaurer la sauvegarde la plus recente utile.

Necessite DATABASE_URL dans .env (comme le reste de l'app).
"""

import json
import sys

from dotenv import load_dotenv

load_dotenv()

from pdc_swim.models import restore_stroke_counts, restore_comments  # noqa: E402


def main():
    if len(sys.argv) != 2:
        print("Usage: python restore_backup.py chemin/vers/pdc_swim_backup.json")
        raise SystemExit(1)

    path = sys.argv[1]
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Compat avec un export ne contenant que les mouvements (sans la cle "stroke_counts"/"comments")
    if isinstance(data, list):
        stroke_counts, comments = data, []
    else:
        stroke_counts = data.get("stroke_counts", [])
        comments = data.get("comments", [])

    n1 = restore_stroke_counts(stroke_counts) if stroke_counts else 0
    n2 = restore_comments(comments) if comments else 0

    print(f"Restauration terminee : {n1} ligne(s) de mouvements, {n2} commentaire(s).")


if __name__ == "__main__":
    main()
