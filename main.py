import sys
import os

# --- GESTION DES CHEMINS (Pour PyInstaller) ---
if getattr(sys, 'frozen', False):
    base_path = sys._MEIPASS
else:
    base_path = os.path.abspath(os.path.dirname(__file__))

# Ajout des dossiers au path pour que Python trouve nos modules
sys.path.append(os.path.join(base_path, 'core'))
sys.path.append(os.path.join(base_path, 'ui'))
sys.path.append(os.path.join(base_path, 'locales'))

# --- CONFIGURATION LANGUE ---
import gettext
import locale

def setup_language():
    try:
        # On tente de récupérer la langue du système (ex: 'fr_FR')
        sys_lang = locale.getdefaultlocale()[0]
        if not sys_lang:
            sys_lang = 'en_US'
    except:
        sys_lang = 'en_US'

    # Configuration du dossier des langues
    locales_dir = os.path.join(base_path, 'locales')
    
    # On initialise la traduction
    # Si la langue n'est pas trouvée, ça reviendra automatiquement à l'anglais (clés du code)
    lang = gettext.translation('base', localedir=locales_dir, languages=[sys_lang], fallback=True)
    lang.install()

# --- LANCEMENT APPLICATION ---
if __name__ == '__main__':
    setup_language()
    
    try:
        import wx
        from ui.main_window import MainWindow

        app = wx.App(False)
        frame = MainWindow()
        frame.Show()
        app.MainLoop()

    except Exception as e:
        # En cas de crash critique au démarrage, on l'écrit dans un fichier log
        # car l'utilisateur ne verra pas la console
        with open("error_log.txt", "w") as f:
            f.write(f"Critical Error: {e}")