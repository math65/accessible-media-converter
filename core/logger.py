import logging
import platform
import sys

from core.debug_session import ensure_debug_dir, get_debug_log_path


def setup_logger(debug_enabled=False):
    root_logger = logging.getLogger()
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)
        try:
            handler.close()
        except Exception:
            pass

    handlers = [logging.StreamHandler(sys.stdout)]
    level = logging.INFO

    if debug_enabled:
        ensure_debug_dir()
        handlers.insert(0, logging.FileHandler(get_debug_log_path(), mode="w", encoding="utf-8"))
        level = logging.DEBUG

    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] [%(filename)s:%(lineno)d] %(message)s",
        datefmt="%H:%M:%S",
        handlers=handlers,
        force=True,
    )

    logging.info("=== SESSION STARTED ===")
    logging.info(f"Debug mode: {'enabled' if debug_enabled else 'disabled'}")
    logging.info(f"OS: {platform.system()} {platform.release()}")
    logging.info(f"Python: {sys.version}")
    if debug_enabled:
        logging.info(f"Debug log path: {get_debug_log_path()}")

    def handle_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        logging.critical("Unhandled exception:", exc_info=(exc_type, exc_value, exc_traceback))

    sys.excepthook = handle_exception
