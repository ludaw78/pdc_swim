"""Envoi d'email (Resend) et endpoint de sauvegarde periodique.

`send_email` est generique : utilise pour la sauvegarde automatique (cron)
et pour les emails de reinitialisation de mot de passe (auth entraineur/admin).

L'endpoint de sauvegarde est une route Starlette brute (pas un event handler
Reflex) car appelee sans session navigateur/cookie - protegee par un jeton
partage (BACKUP_TOKEN), independant du systeme de login coach/admin.

Variables d'environnement attendues :
    RESEND_API_KEY      cle API Resend (https://resend.com)
    RESEND_FROM_EMAIL     optionnel, defaut sur le domaine sandbox Resend
    BACKUP_TOKEN       chaine aleatoire longue, secret partage avec le cron
    ADMIN_EMAIL          destinataire de la sauvegarde
"""

import base64
import json
import os
import urllib.request

from starlette.requests import Request
from starlette.responses import JSONResponse

from .models import export_all_stroke_counts, export_all_comments

RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
RESEND_FROM_EMAIL = os.environ.get("RESEND_FROM_EMAIL", "onboarding@resend.dev")

BACKUP_TOKEN = os.environ.get("BACKUP_TOKEN", "")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "ludovic.bourdin@gmail.com")


def send_email(to: str, subject: str, text: str, attachment: tuple[str, str] | None = None) -> None:
    """Envoie un email via l'API Resend.

    attachment : tuple optionnel (filename, contenu texte) joint au message.
    Leve une exception si RESEND_API_KEY absente ou si Resend refuse.
    """
    if not RESEND_API_KEY:
        raise RuntimeError("RESEND_API_KEY absente")
    payload = {
        "from": f"PdC Swim <{RESEND_FROM_EMAIL}>",
        "to": [to],
        "subject": subject,
        "text": text,
    }
    if attachment is not None:
        filename, content = attachment
        payload["attachments"] = [{
            "filename": filename,
            "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
        }]
    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {RESEND_API_KEY}",
            "Content-Type": "application/json",
            # Sans User-Agent explicite, Cloudflare (devant l'API Resend) bloque
            # la requete comme un bot (erreur 1010) - voir diagnostic du 09/08/2026.
            "User-Agent": "pdc-swim-app/1.0",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        if resp.status >= 300:
            raise RuntimeError(f"Resend a répondu {resp.status}")


def run_backup() -> dict:
    """Exporte toutes les donnees entraineur et les envoie par email.

    Partagee entre l'endpoint cron (backup_endpoint) et le bouton "sauvegarde
    manuelle" reserve a l'admin (State.trigger_backup_now dans pdc_swim.py).
    Leve une exception si l'envoi echoue (RESEND_API_KEY absente, Resend en
    erreur, etc.) - a l'appelant de la traiter.
    """
    data = {
        "stroke_counts": export_all_stroke_counts(),
        "comments": export_all_comments(),
    }
    n_rows = len(data["stroke_counts"]) + len(data["comments"])
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    send_email(
        ADMIN_EMAIL,
        f"Sauvegarde PdC Swim - {n_rows} entrées",
        f"Sauvegarde en pièce jointe ({len(data['stroke_counts'])} mouvements, {len(data['comments'])} commentaires).",
        attachment=("pdc_swim_backup.json", payload),
    )
    return {"status": "ok", "rows": n_rows}


async def backup_endpoint(request: Request) -> JSONResponse:
    if not BACKUP_TOKEN or request.query_params.get("token") != BACKUP_TOKEN:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    try:
        return JSONResponse(run_backup())
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
