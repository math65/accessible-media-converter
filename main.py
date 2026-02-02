import sys
import os
import wx

# --- GESTION DES CHEMINS ---
if getattr(sys, 'frozen', False):
    base_path = sys._MEIPASS
else:
    base_path = os.path.abspath(os.path.dirname(__file__))

# On ajoute les dossiers au path pour que Python trouve nos modules
sys.path.append(os.path.join(base_path, 'core'))
sys.path.append(os.path.join(base_path, 'ui'))

# --- IMPORTATION ET ACTIVATION DE LA LANGUE ---
# C'est ici qu'on utilise ton fichier core/i18n.py
try:
    from core.i18n import install_language
    install_language()
except Exception as e:
    # Si polib manque ou autre erreur, on log et on continue en anglais par défaut
    print(f"Warning: Language setup failed: {e}")

# --- LANCEMENT APPLICATION ---
if __name__ == '__main__':
    try:
        # On importe l'interface seulement APRES avoir installé la langue
        from ui.main_window import MainWindow

        app = wx.App(False)
        frame = MainWindow()
        frame.Show()
        app.MainLoop()

    except Exception as e:
        with open("error_log.txt", "w") as f:
            f.write(f"Critical Error: {e}")