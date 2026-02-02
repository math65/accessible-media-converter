import logging
import os
import sys
import platform

# Chemin du fichier de log (à côté du main.py)
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(os.path.join(__file__, '..')))

LOG_FILE = os.path.join(BASE_DIR, "debug.log")

def setup_logger():
    # On supprime l'ancien log à chaque démarrage pour y voir clair
    if os.path.exists(LOG_FILE):
        try:
            os.remove(LOG_FILE)
        except: pass

    # Configuration du format : [HEURE] [NIVEAU] [FICHIER] Message
    log_format = "%(asctime)s [%(levelname)s] [%(filename)s:%(lineno)d] %(message)s"
    date_format = "%H:%M:%S"

    # On capture TOUT (DEBUG est le niveau le plus bas)
    logging.basicConfig(
        level=logging.DEBUG,
        format=log_format,
        datefmt=date_format,
        handlers=[
            logging.FileHandler(LOG_FILE, mode='w', encoding='utf-8'), # Écrit dans le fichier
            logging.StreamHandler(sys.stdout) # Écrit aussi dans la console
        ]
    )

    logging.info("=== DÉMARRAGE DE LA SESSION DE LOG ===")
    logging.info(f"OS: {platform.system()} {platform.release()}")
    logging.info(f"Python: {sys.version}")
    logging.info(f"Dossier de base: {BASE_DIR}")

    # Capture des exceptions non gérées (Crashs brutaux)
    def handle_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        logging.critical("CRASH NON GÉRÉ (Uncaught Exception):", exc_info=(exc_type, exc_value, exc_traceback))

    sys.excepthook = handle_exception