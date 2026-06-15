"""
Annonces au lancement (Accessible Media Converter).

Interroge le backend partagé app-backend (route générique /api/announce/check)
et, si une annonce active existe, la remonte à l'UI pour affichage. Confirme
l'affichage via /api/announce/ack. Vérification silencieuse : toute erreur réseau
est ignorée (la feature ne doit jamais gêner le démarrage). Calqué sur le client
DownAccess (dl/app/core/announce.py).
"""
import json
import logging
import threading
import urllib.error
import urllib.request

from core import i18n
from core.support import _APP_ID, _BEARER

log = logging.getLogger("amc.announce")

CHECK_URL = "https://mathieumartin.ovh/api/announce/check"
ACK_URL = "https://mathieumartin.ovh/api/announce/ack"
CLICK_URL = "https://mathieumartin.ovh/api/announce/click"


def _post(url, payload, timeout):
    """POST JSON avec auth Bearer, retourne le corps décodé."""
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json; charset=utf-8")
    req.add_header("Authorization", f"Bearer {_BEARER}")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def check_announcement(install_id, on_done):
    """
    Récupère l'annonce active pour AMC en arrière-plan.

    on_done(announcement | None) est appelé depuis le thread — utiliser
    wx.CallAfter côté UI. None = aucune annonce ou erreur (silencieux).
    """
    def _run():
        try:
            lang = i18n.get_current_language_code()
            payload = {"app": _APP_ID, "install_id": install_id, "lang": lang}
            body = _post(CHECK_URL, payload, timeout=8)
            ann = body.get("announcement")
            on_done(ann if isinstance(ann, dict) else None)
        except (urllib.error.URLError, OSError, ValueError) as exc:
            log.debug("Verification annonce impossible : %s", exc)
            on_done(None)
        except Exception as exc:
            log.debug("Verification annonce : erreur inattendue : %s", exc)
            on_done(None)

    threading.Thread(target=_run, daemon=True).start()


def ack_announcement(install_id, ann_id):
    """Confirme l'affichage d'une annonce (fire-and-forget, erreurs ignorées)."""
    def _run():
        try:
            _post(ACK_URL, {"app": _APP_ID, "install_id": install_id, "id": ann_id}, timeout=8)
        except Exception as exc:
            log.debug("Accuse annonce impossible : %s", exc)

    threading.Thread(target=_run, daemon=True).start()


def click_announcement(install_id, ann_id):
    """Enregistre un clic sur le bouton lien de l'annonce (fire-and-forget)."""
    def _run():
        try:
            _post(CLICK_URL, {"app": _APP_ID, "install_id": install_id, "id": ann_id}, timeout=8)
        except Exception as exc:
            log.debug("Clic annonce impossible : %s", exc)

    threading.Thread(target=_run, daemon=True).start()
