import wx
import gettext
import os
import sys
import logging

# On importe notre nouveau logger
from core.logger import setup_logger

# --- CONFIGURATION LANGUE (GETTEXT) ---
def init_i18n():
    logging.debug("Initialisation du système de traduction...")
    if getattr(sys, 'frozen', False):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    
    locale_dir = os.path.join(base_path, 'locales')
    logging.debug(f"Dossier locales détecté : {locale_dir}")
    
    import builtins
    try:
        lang = gettext.translation('base', localedir=locale_dir, languages=['fr'])
        lang.install()
        logging.info("Langue 'fr' chargée avec succès.")
    except Exception as e:
        logging.warning(f"Échec du chargement de la langue : {e}. Fallback sur anglais.")
        builtins.__dict__['_'] = lambda s: s

def main():
    # 1. D'ABORD : On allume les micros (Logger)
    setup_logger()
    
    try:
        # 2. On active la langue
        init_i18n()
        
        logging.info("Importation de l'interface graphique...")
        from ui.main_window import MainWindow
        
        logging.info("Démarrage de wx.App...")
        app = wx.App(False)
        
        logging.info("Création de la fenêtre principale...")
        frame = MainWindow()
        frame.Show()
        
        logging.info("Entrée dans la boucle principale (MainLoop)...")
        app.MainLoop()
        
    except Exception as e:
        logging.critical("Erreur critique dans le main :", exc_info=True)
        raise e

    logging.info("=== APPLICATION FERMÉE PROPREMENT ===")

if __name__ == '__main__':
    main()