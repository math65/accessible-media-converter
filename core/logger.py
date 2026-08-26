import logging
import logging.handlers
import os
import platform
import sys

from core.debug_session import get_config_dir

# Journal fichier tournant dans %APPDATA%\AccessibleMediaConverter.
#
# Jusqu'en v1.20.4 le logger n'avait qu'un StreamHandler vers stdout, et l'exe
# packagé n'a pas de console : rien n'était jamais écrit sur disque. Aucun bug
# terrain n'était donc traçable a posteriori (cf. l'affaire des MP4 à l'audio
# amputé d'août 2026 : impossible de savoir quelles conversions avaient tourné).
LOG_FILE_NAME = "debug.log"
LOG_MAX_BYTES = 1_000_000
LOG_BACKUP_COUNT = 2
# Taille du extrait joint aux rapports : on garde la FIN du journal (les
# événements les plus proches de l'incident).
REPORT_LOG_MAX_BYTES = 400_000

LOG_FORMAT = "%(asctime)s [%(levelname)s] [%(filename)s:%(lineno)d] %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_log_file_path = None


def get_log_file_path():
    """Chemin du journal actif, ou None si le fichier n'a pas pu être ouvert."""
    return _log_file_path


def _build_stream_handler():
    stream = sys.stdout if sys.stdout is not None else open(os.devnull, 'w')
    return logging.StreamHandler(stream=stream)


def _build_file_handler():
    """Handler fichier tournant. Renvoie (handler, chemin) ou (None, None).

    Ne doit jamais empêcher l'application de démarrer : un disque plein, un
    %APPDATA% en lecture seule ou un antivirus qui verrouille le fichier
    dégradent simplement le journal vers stdout.
    """
    try:
        directory = get_config_dir()
        os.makedirs(directory, exist_ok=True)
        path = os.path.join(directory, LOG_FILE_NAME)
        handler = logging.handlers.RotatingFileHandler(
            path,
            maxBytes=LOG_MAX_BYTES,
            backupCount=LOG_BACKUP_COUNT,
            encoding='utf-8',
        )
        return handler, path
    except Exception:
        return None, None


def setup_logger():
    global _log_file_path

    root_logger = logging.getLogger()
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)
        try:
            handler.close()
        except Exception:
            pass

    formatter = logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT)
    handlers = [_build_stream_handler()]

    file_handler, _log_file_path = _build_file_handler()
    if file_handler is not None:
        handlers.append(file_handler)

    for handler in handlers:
        handler.setFormatter(formatter)

    logging.basicConfig(level=logging.INFO, handlers=handlers, force=True)

    logging.info("=== SESSION STARTED ===")
    logging.info(f"OS: {platform.system()} {platform.release()}")
    logging.info(f"Python: {sys.version}")
    if _log_file_path:
        logging.info("Journal : %s", _log_file_path)
    else:
        logging.warning("Journal fichier indisponible : sortie console uniquement.")

    def handle_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        logging.critical("Unhandled exception:", exc_info=(exc_type, exc_value, exc_traceback))

    sys.excepthook = handle_exception


def read_log_tail(max_bytes=REPORT_LOG_MAX_BYTES):
    """Fin du journal applicatif, pour jonction à un rapport. '' si indisponible."""
    path = _log_file_path
    if not path:
        return ""
    try:
        for handler in logging.getLogger().handlers:
            try:
                handler.flush()
            except Exception:
                pass
        size = os.path.getsize(path)
        with open(path, 'r', encoding='utf-8', errors='replace') as handle:
            if size > max_bytes:
                handle.seek(size - max_bytes)
                handle.readline()  # repart sur une ligne entière
            return handle.read()
    except Exception:
        return ""
