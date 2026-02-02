import sys
import traceback

print("--- Starting Universal Transcoder ---")

try:
    # 1. Import wxPython
    import wx
    print("[OK] wxPython imported")

    # 2. Setup Language (Must be done BEFORE importing UI)
    from core import i18n
    print("[...] Loading language")
    i18n.install_language()
    print("[OK] Language loaded")

    # 3. Import UI
    from ui.main_window import MainWindow
    print("[OK] UI imported")

    if __name__ == "__main__":
        print("[...] Starting Main Loop")
        app = wx.App()
        frame = MainWindow()
        frame.Show()
        app.MainLoop()

except Exception:
    # Catch any startup error and keep window open
    print("\n!!!!!!!!!!!!!!!! CRASH !!!!!!!!!!!!!!!!")
    traceback.print_exc()
    print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
    input("\nPress Enter to close...")