import gettext
import os
import sys
import locale
import polib

def install_language():
    # 1. Chemins
    if getattr(sys, 'frozen', False):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    
    locales_dir = os.path.join(base_path, 'locales')

    # 2. Compilation auto en dev
    if not getattr(sys, 'frozen', False):
        _compile_automatic(locales_dir)

    # 3. Détection langue
    try:
        sys_lang = locale.getdefaultlocale()[0]
        lang_code = 'fr' if sys_lang and sys_lang.startswith('fr') else 'en'
    except:
        lang_code = 'en'

    # 4. Installation
    try:
        lang = gettext.translation('base', localedir=locales_dir, languages=[lang_code])
        lang.install()
    except Exception:
        gettext.install('base', localedir=locales_dir)

def _compile_automatic(locales_dir):
    for root, dirs, files in os.walk(locales_dir):
        for file in files:
            if file.endswith('.po'):
                try:
                    po_path = os.path.join(root, file)
                    po = polib.pofile(po_path)
                    po.save_as_mofile(po_path.replace('.po', '.mo'))
                except:
                    pass