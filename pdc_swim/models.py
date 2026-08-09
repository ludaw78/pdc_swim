"""Données saisies par l'entraîneur, persistées côté serveur (Neon/Postgres).

Séparé de pdc_swim.py car zéro dépendance UI : Alembic (reflex db ...) a besoin
d'un chemin d'import stable pour découvrir les modèles, et cette logique est
testable isolément du reste de l'app.
"""

from datetime import datetime, timezone

import reflex as rx
import sqlmodel
from sqlmodel import UniqueConstraint, select


class RaceStrokeCount(rx.Model, table=True):
    """Nombre de coups de bras pour une longueur donnée d'une course.

    Une ligne par longueur (length_index = position dans dialog_splits_data,
    0-based). La clé (swimmer_key, date, epreuve, bassin, temps) identifie la
    course de façon stable — voir open_dialog() dans pdc_swim.py.
    """

    swimmer_key: str = sqlmodel.Field(index=True)
    date: str          # == Result.D  "dd/mm/yyyy"
    epreuve: str        # == Result.E
    bassin: str          # == Result.B  "25m"/"50m"
    temps: str            # == Result.T
    length_index: int       # position dans dialog_splits_data (0-based)
    dist_label: str = ""     # SplitRow.dist, pour lisibilité export/debug
    stroke_count: int
    updated_by: str = ""      # username du token vérifié (coach/admin)
    updated_at: str = ""       # ISO timestamp UTC

    __table_args__ = (
        UniqueConstraint(
            "swimmer_key", "date", "epreuve", "bassin", "temps", "length_index",
            name="uq_race_stroke_count_key",
        ),
    )


def load_stroke_counts(
    swimmer_key: str, date: str, epreuve: str, bassin: str, temps: str, n_rows: int
) -> list[str]:
    """Lit les coups de bras déjà enregistrés pour une course.

    Retourne une liste de taille n_rows (une entrée par longueur), "" si
    aucune valeur n'a encore été saisie pour cette longueur.
    """
    result = [""] * n_rows
    if n_rows <= 0:
        return result
    with rx.session() as session:
        rows = session.exec(
            select(RaceStrokeCount).where(
                RaceStrokeCount.swimmer_key == swimmer_key,
                RaceStrokeCount.date == date,
                RaceStrokeCount.epreuve == epreuve,
                RaceStrokeCount.bassin == bassin,
                RaceStrokeCount.temps == temps,
            )
        ).all()
    for row in rows:
        if 0 <= row.length_index < n_rows:
            result[row.length_index] = str(row.stroke_count)
    return result


def save_stroke_counts(
    swimmer_key: str,
    date: str,
    epreuve: str,
    bassin: str,
    temps: str,
    dist_labels: list[str],
    values: list[str],
    username: str,
) -> None:
    """Enregistre (insert, update ou suppression si vide) les coups de bras saisis par le coach.

    Un champ vide efface la ligne correspondante en base (plutot que de laisser
    trainer l'ancienne valeur), pour permettre de corriger une saisie.
    """
    now = datetime.now(timezone.utc).isoformat()
    with rx.session() as session:
        for idx, val in enumerate(values):
            existing = session.exec(
                select(RaceStrokeCount).where(
                    RaceStrokeCount.swimmer_key == swimmer_key,
                    RaceStrokeCount.date == date,
                    RaceStrokeCount.epreuve == epreuve,
                    RaceStrokeCount.bassin == bassin,
                    RaceStrokeCount.temps == temps,
                    RaceStrokeCount.length_index == idx,
                )
            ).first()
            if val == "":
                if existing:
                    session.delete(existing)
                continue
            if existing:
                existing.stroke_count = int(val)
                existing.updated_by = username
                existing.updated_at = now
                session.add(existing)
            else:
                session.add(
                    RaceStrokeCount(
                        swimmer_key=swimmer_key,
                        date=date,
                        epreuve=epreuve,
                        bassin=bassin,
                        temps=temps,
                        length_index=idx,
                        dist_label=dist_labels[idx] if idx < len(dist_labels) else "",
                        stroke_count=int(val),
                        updated_by=username,
                        updated_at=now,
                    )
                )
        session.commit()


def export_all_stroke_counts() -> list[dict]:
    """Dump complet de la table, pour la sauvegarde périodique."""
    with rx.session() as session:
        rows = session.exec(select(RaceStrokeCount)).all()
        return [row.model_dump() for row in rows]


def restore_stroke_counts(rows: list[dict]) -> int:
    """Reinjecte un export (JSON issu de export_all_stroke_counts) dans la table.

    Upsert par cle composite (pas d'ecrasement total de la table) - utilise pour
    une restauration apres incident. Retourne le nombre de lignes traitees.
    """
    count = 0
    with rx.session() as session:
        for row in rows:
            existing = session.exec(
                select(RaceStrokeCount).where(
                    RaceStrokeCount.swimmer_key == row["swimmer_key"],
                    RaceStrokeCount.date == row["date"],
                    RaceStrokeCount.epreuve == row["epreuve"],
                    RaceStrokeCount.bassin == row["bassin"],
                    RaceStrokeCount.temps == row["temps"],
                    RaceStrokeCount.length_index == row["length_index"],
                )
            ).first()
            if existing:
                existing.stroke_count = row["stroke_count"]
                existing.dist_label = row.get("dist_label", existing.dist_label)
                existing.updated_by = row.get("updated_by", existing.updated_by)
                existing.updated_at = row.get("updated_at", existing.updated_at)
                session.add(existing)
            else:
                session.add(RaceStrokeCount(**{k: v for k, v in row.items() if k != "id"}))
            count += 1
        session.commit()
    return count


class RaceComment(rx.Model, table=True):
    """Commentaire de l'entraineur sur une course (un par course, pas par longueur)."""

    swimmer_key: str = sqlmodel.Field(index=True)
    date: str
    epreuve: str
    bassin: str
    temps: str
    comment: str = ""
    updated_by: str = ""
    updated_at: str = ""

    __table_args__ = (
        UniqueConstraint(
            "swimmer_key", "date", "epreuve", "bassin", "temps",
            name="uq_race_comment_key",
        ),
    )


def load_comment(swimmer_key: str, date: str, epreuve: str, bassin: str, temps: str) -> str:
    with rx.session() as session:
        row = session.exec(
            select(RaceComment).where(
                RaceComment.swimmer_key == swimmer_key,
                RaceComment.date == date,
                RaceComment.epreuve == epreuve,
                RaceComment.bassin == bassin,
                RaceComment.temps == temps,
            )
        ).first()
        return row.comment if row else ""


def save_comment(
    swimmer_key: str, date: str, epreuve: str, bassin: str, temps: str,
    comment: str, username: str,
) -> None:
    """Enregistre (insert ou update) le commentaire d'une course. Autorise la remise a vide."""
    now = datetime.now(timezone.utc).isoformat()
    with rx.session() as session:
        existing = session.exec(
            select(RaceComment).where(
                RaceComment.swimmer_key == swimmer_key,
                RaceComment.date == date,
                RaceComment.epreuve == epreuve,
                RaceComment.bassin == bassin,
                RaceComment.temps == temps,
            )
        ).first()
        if existing:
            existing.comment = comment
            existing.updated_by = username
            existing.updated_at = now
            session.add(existing)
        else:
            session.add(RaceComment(
                swimmer_key=swimmer_key, date=date, epreuve=epreuve, bassin=bassin, temps=temps,
                comment=comment, updated_by=username, updated_at=now,
            ))
        session.commit()


def export_all_comments() -> list[dict]:
    """Dump complet de la table, pour la sauvegarde périodique."""
    with rx.session() as session:
        rows = session.exec(select(RaceComment)).all()
        return [row.model_dump() for row in rows]


def restore_comments(rows: list[dict]) -> int:
    """Reinjecte un export (JSON issu de export_all_comments) dans la table.

    Upsert par cle composite - utilise pour une restauration apres incident.
    """
    count = 0
    with rx.session() as session:
        for row in rows:
            existing = session.exec(
                select(RaceComment).where(
                    RaceComment.swimmer_key == row["swimmer_key"],
                    RaceComment.date == row["date"],
                    RaceComment.epreuve == row["epreuve"],
                    RaceComment.bassin == row["bassin"],
                    RaceComment.temps == row["temps"],
                )
            ).first()
            if existing:
                existing.comment = row.get("comment", "")
                existing.updated_by = row.get("updated_by", existing.updated_by)
                existing.updated_at = row.get("updated_at", existing.updated_at)
                session.add(existing)
            else:
                session.add(RaceComment(**{k: v for k, v in row.items() if k != "id"}))
            count += 1
        session.commit()
    return count


class User(rx.Model, table=True):
    """Compte entraineur/admin. 2 comptes geres a la main (pas d'auto-inscription)."""

    username: str = sqlmodel.Field(unique=True, index=True)
    email: str = sqlmodel.Field(unique=True, index=True)
    password_hash: str
    role: str  # "coach" ou "admin"


def get_user_by_username(username: str) -> User | None:
    if not username:
        return None
    with rx.session() as session:
        return session.exec(select(User).where(User.username == username)).first()


def get_user_by_email(email: str) -> User | None:
    if not email:
        return None
    with rx.session() as session:
        return session.exec(select(User).where(User.email == email)).first()


def update_password_hash(username: str, new_hash: str) -> bool:
    """Met a jour le hash de mot de passe d'un compte existant. False si le compte n'existe pas."""
    with rx.session() as session:
        user = session.exec(select(User).where(User.username == username)).first()
        if user is None:
            return False
        user.password_hash = new_hash
        session.add(user)
        session.commit()
        return True
