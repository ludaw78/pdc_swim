"""Crypto/tokens pour l'authentification entraineur/admin.

Module pur Python (pas de dependance Reflex ni DB) : le hashing/verification
de mot de passe et la signature des tokens vivent ici, testables isolement.
La recherche des comptes en base vit dans models.py (get_user_by_username
etc.) ; l'orchestration (verifier le mot de passe d'un User trouve en DB,
poser le cookie) vit dans les handlers de State (pdc_swim.py).

Variables d'environnement attendues (dans .env en local, dans les settings
du projet sur Reflex Cloud en prod) :
    SECRET_KEY   cle de signature des tokens de session ET de reinitialisation

Pour generer un hash bcrypt localement :
    python -c "import bcrypt; print(bcrypt.hashpw(b'le-mot-de-passe', bcrypt.gensalt()).decode())"
"""

import os

import bcrypt
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

SECRET_KEY = os.environ.get("SECRET_KEY", "")

TOKEN_MAX_AGE = 60 * 60 * 24 * 180  # 180 jours (session de connexion)
RESET_TOKEN_MAX_AGE = 60 * 60  # 1h (lien de reinitialisation de mot de passe)

_session_serializer = URLSafeTimedSerializer(SECRET_KEY, salt="pdc-swim-auth") if SECRET_KEY else None
_reset_serializer = URLSafeTimedSerializer(SECRET_KEY, salt="pdc-swim-reset") if SECRET_KEY else None


def hash_password(password: str) -> str:
    """Hash un mot de passe en clair (bcrypt, sale)."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def check_password(password: str, password_hash: str) -> bool:
    """Verifie un mot de passe en clair contre un hash bcrypt existant."""
    if not password or not password_hash:
        return False
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except ValueError:
        # hash mal forme -> jamais de match, pas de crash
        return False


def make_token(username: str, role: str) -> str:
    """Cree un token de session signe. Chaine vide si SECRET_KEY absente."""
    if _session_serializer is None:
        return ""
    return _session_serializer.dumps({"u": username, "r": role})


def verify_token(token: str) -> dict | None:
    """Verifie un token de session. None si absent, invalide, expire ou falsifie."""
    if not token or _session_serializer is None:
        return None
    try:
        data = _session_serializer.loads(token, max_age=TOKEN_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None
    if not isinstance(data, dict):
        return None
    return {"username": data.get("u", ""), "role": data.get("r", "")}


def make_reset_token(username: str) -> str:
    """Cree un token de reinitialisation de mot de passe, valable 1h."""
    if _reset_serializer is None:
        return ""
    return _reset_serializer.dumps({"u": username})


def verify_reset_token(token: str) -> str | None:
    """Verifie un token de reinitialisation. Retourne le username, ou None si invalide/expire."""
    if not token or _reset_serializer is None:
        return None
    try:
        data = _reset_serializer.loads(token, max_age=RESET_TOKEN_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None
    if not isinstance(data, dict):
        return None
    return data.get("u") or None
