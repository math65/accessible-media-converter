import os
import sys
import webbrowser
from pathlib import Path

from core.i18n import get_current_language_code, normalize_ui_language

DOCUMENTATION_FALLBACK_LANGUAGES = ("en", "fr")


def get_documentation_base_path():
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS"))
    return Path(__file__).resolve().parent.parent


def get_documentation_index_path(language):
    return get_documentation_base_path() / "docs" / language / "index.html"


def get_documentation_language_candidates(language=None):
    if language is None:
        requested_language = get_current_language_code()
    else:
        requested_language = normalize_ui_language(language)
        if requested_language == "auto":
            requested_language = get_current_language_code()

    candidates = [requested_language, *DOCUMENTATION_FALLBACK_LANGUAGES]
    unique_candidates = []
    for candidate in candidates:
        if candidate not in unique_candidates:
            unique_candidates.append(candidate)
    return tuple(unique_candidates)


def resolve_documentation_index_path(language=None):
    candidates = get_documentation_language_candidates(language)
    primary_path = get_documentation_index_path(candidates[0]).resolve()

    for candidate in candidates:
        doc_path = get_documentation_index_path(candidate).resolve()
        if doc_path.exists():
            return doc_path, candidate, ""

    return primary_path, candidates[0], "missing"


def open_documentation(language=None):
    doc_path, _language_used, error_code = resolve_documentation_index_path(language)
    doc_path = doc_path.resolve()
    if error_code == "missing":
        return False, str(doc_path), "missing"

    if not doc_path.exists():
        return False, str(doc_path), "missing"

    try:
        if os.name == "nt" and hasattr(os, "startfile"):
            os.startfile(str(doc_path))
            return True, str(doc_path), ""
        if webbrowser.open(doc_path.as_uri()):
            return True, str(doc_path), ""
    except Exception:
        return False, str(doc_path), "open_failed"

    return False, str(doc_path), "open_failed"
