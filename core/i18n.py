import builtins
import gettext
import locale
import os
import sys

try:
    import polib
except Exception:
    polib = None

CURRENT_LANGUAGE_CODE = "en"
CURRENT_LANGUAGE_SOURCE = "fallback"


def install_language(preferred_lang='fr', prefer_po=True):
    global CURRENT_LANGUAGE_CODE
    global CURRENT_LANGUAGE_SOURCE

    if getattr(sys, 'frozen', False):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

    locales_dir = os.path.join(base_path, 'locales')
    lang_code = _resolve_language(preferred_lang)

    # In development, load .po directly to avoid manual compile steps.
    if prefer_po and not getattr(sys, 'frozen', False):
        if _install_from_po(locales_dir, lang_code):
            CURRENT_LANGUAGE_CODE = lang_code
            CURRENT_LANGUAGE_SOURCE = 'po'
            return lang_code, 'po'

    try:
        lang = gettext.translation('base', localedir=locales_dir, languages=[lang_code])
        lang.install()
        CURRENT_LANGUAGE_CODE = lang_code
        CURRENT_LANGUAGE_SOURCE = 'mo'
        return lang_code, 'mo'
    except Exception:
        gettext.install('base', localedir=locales_dir)
        builtins.__dict__.setdefault('_', lambda s: s)
        CURRENT_LANGUAGE_CODE = 'en'
        CURRENT_LANGUAGE_SOURCE = 'fallback'
        return 'en', 'fallback'


def get_current_language_code():
    return CURRENT_LANGUAGE_CODE


def get_current_language_source():
    return CURRENT_LANGUAGE_SOURCE


def _resolve_language(preferred_lang):
    if preferred_lang:
        return preferred_lang
    try:
        sys_lang = locale.getlocale()[0] or locale.getdefaultlocale()[0]
        return 'fr' if sys_lang and sys_lang.lower().startswith('fr') else 'en'
    except Exception:
        return 'en'


def _install_from_po(locales_dir, lang_code):
    if polib is None:
        return False

    po_path = os.path.join(locales_dir, lang_code, 'LC_MESSAGES', 'base.po')
    if not os.path.exists(po_path):
        return False

    try:
        po = polib.pofile(po_path)
        mapping = {}
        for entry in po:
            if entry.obsolete:
                continue
            if entry.msgid_plural:
                mapping[entry.msgid] = entry.msgstr_plural.get('0', entry.msgid)
            elif entry.msgstr:
                mapping[entry.msgid] = entry.msgstr

        builtins.__dict__['_'] = lambda s: mapping.get(s, s)
        return True
    except Exception:
        return False
