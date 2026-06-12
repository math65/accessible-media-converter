"""Retour vocal optionnel via accessible_output2 (NVDA / JAWS / SAPI…).

Sécurisé par conception : toute erreur d'initialisation ou de synthèse est
avalée — le retour vocal ne doit jamais casser l'UI. L'instance Auto est créée
paresseusement au premier appel et réutilisée ensuite.
"""

import logging

_speaker = None
_init_failed = False


def speak(message, interrupt=True):
    """Annonce un message via le lecteur d'écran actif (SAPI en repli).

    No-op silencieux si accessible_output2 est indisponible ou si aucun moteur
    ne répond. `interrupt=True` coupe l'annonce précédente (utile pour des
    actions répétées rapidement, ex. réordonnancement)."""
    global _speaker, _init_failed
    if not message or _init_failed:
        return
    if _speaker is None:
        try:
            from accessible_output2.outputs.auto import Auto
            _speaker = Auto()
        except Exception:
            _init_failed = True
            logging.debug("Retour vocal indisponible (accessible_output2).", exc_info=True)
            return
    try:
        _speaker.speak(message, interrupt=interrupt)
    except Exception:
        logging.debug("Échec de la synthèse vocale.", exc_info=True)
