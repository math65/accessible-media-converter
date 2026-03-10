import wx
import os
import sys
import logging

from core.debug_session import get_debug_flags, load_raw_config
# On importe notre nouveau logger
from core.logger import setup_logger
from core.i18n import AUTO_LANGUAGE_CODE
from core.i18n import install_language
from core.updater import cleanup_update_artifacts

# --- CONFIGURATION LANGUE (GETTEXT) ---
def init_i18n(config_data=None):
    logging.debug("Initialisation du système de traduction...")
    if getattr(sys, 'frozen', False):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    locale_dir = os.path.join(base_path, 'locales')
    logging.debug(f"Dossier locales détecté : {locale_dir}")

    try:
        preferred_lang = AUTO_LANGUAGE_CODE
        if isinstance(config_data, dict):
            preferred_lang = config_data.get("ui_language", AUTO_LANGUAGE_CODE)
        lang_code, source = install_language(preferred_lang=preferred_lang, prefer_po=True)
        logging.info(f"Langue '{lang_code}' chargée depuis: {source}.")
    except Exception as e:
        logging.warning(f"Échec du chargement de la langue : {e}. Fallback sur anglais.")

def main():
    raw_config = load_raw_config()
    debug_flags = get_debug_flags(raw_config)
    setup_logger(debug_enabled=debug_flags['debug_enabled'])
    removed_update_artifacts = cleanup_update_artifacts()
    if removed_update_artifacts:
        logging.info("Updater cleanup removed %s artifact(s).", len(removed_update_artifacts))
    
    try:
        init_i18n(raw_config)
        
        logging.info("Importation de l'interface graphique...")
        from ui.main_window import MainWindow
        
        logging.info("Démarrage de wx.App...")
        app = wx.App(False)
        
        logging.info("Création de la fenêtre principale...")
        frame = MainWindow()
        if debug_flags['restore_pending']:
            frame.restore_session_if_needed()
        frame.Show()
        frame.schedule_startup_update_check()
        
        logging.info("Entrée dans la boucle principale (MainLoop)...")
        app.MainLoop()
        
    except Exception as e:
        logging.critical("Erreur critique dans le main :", exc_info=True)
        raise e

    logging.info("=== APPLICATION FERMÉE PROPREMENT ===")

if __name__ == '__main__':
    main()
