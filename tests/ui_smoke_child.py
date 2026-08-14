"""Instancie la fenêtre principale et chaque dialogue, sans jamais les afficher.

Lancé en sous-processus par `tests/test_ui_smoke.py` : wxWidgets écrit ses
avertissements sur la sortie d'erreur *native*, qu'on ne peut lire proprement
qu'en isolant le processus.

Sortie : une ligne par dialogue, puis « ECHECS: N ».
"""

import sys

from tests.helpers import audio_track, make_media, subtitle_track, video_track

import wx

from core.debug_session import load_raw_config
from main import init_i18n

init_i18n(load_raw_config())
app = wx.App(False)

from ui.main_window import MainWindow  # noqa: E402  (après wx.App)

frame = MainWindow()
results = []


def check(label, factory):
    try:
        window = factory()
        if isinstance(window, wx.Window):
            window.Destroy()
        results.append(("OK  ", label))
    except Exception as exc:
        results.append(("FAIL", f"{label} -> {type(exc).__name__}: {exc}"))


from core.updater import ReleaseInfo  # noqa: E402
from ui.announcement_dialog import AnnouncementDialog  # noqa: E402
from ui.error_report_dialog import ErrorReportDialog  # noqa: E402
from ui.metadata_editor import MetadataEditorDialog  # noqa: E402
from ui.preferences_dialog import PreferencesDialog  # noqa: E402
from ui.presets_dialog import PresetsDialog  # noqa: E402
from ui.settings_dialog import SettingsDialog  # noqa: E402
from ui.support_dialog import SupportContactDialog  # noqa: E402
from ui.track_manager import AudioExtractTrackDialog, TrackManagerDialog  # noqa: E402
from ui.update_dialog import UpdateDialog  # noqa: E402

meta = make_media(
    video=[video_track(0)],
    audio=[audio_track(1), audio_track(2)],
    subtitle=[subtitle_track(3)],
)
store = frame.settings_store
release = ReleaseInfo(
    tag_name="v9.9.9", version="9.9.9", published_at="2026-01-01T00:00:00Z",
    html_url="https://example.invalid", body="notes",
    asset_name="AccessibleMediaConverter-Setup.exe", asset_url="https://example.invalid",
)

check("MainWindow", lambda: None)
check("TrackManagerDialog", lambda: TrackManagerDialog(frame, meta))
check("AudioExtractTrackDialog", lambda: AudioExtractTrackDialog(frame, meta, None))
check("SettingsDialog (mp3)", lambda: SettingsDialog(frame, "MP3", False, 2, store, "mp3"))
check("SettingsDialog (mp4)", lambda: SettingsDialog(frame, "MP4", True, 2, store, "mp4"))
check("SettingsDialog (jpeg)", lambda: SettingsDialog(frame, "JPEG", False, 0, store, "jpeg"))
check("MetadataEditorDialog", lambda: MetadataEditorDialog(frame, [meta], "mp4"))
check("PreferencesDialog", lambda: PreferencesDialog(frame, store))
check("PresetsDialog", lambda: PresetsDialog(frame, "audio", "mp3", store, {}))
check("SupportContactDialog", lambda: SupportContactDialog(frame))
check("UpdateDialog", lambda: UpdateDialog(frame, release))
check(
    "ErrorReportDialog",
    lambda: ErrorReportDialog(
        frame,
        {"input_path": "film.mp4", "target_format": "mp4", "ffmpeg_command": [],
         "ffmpeg_stderr": "", "error_message": "boom"},
        store,
    ),
)
check(
    "AnnouncementDialog",
    lambda: AnnouncementDialog(frame, "Titre", "Corps", "Lien", "https://example.invalid", None),
)

for status, label in results:
    print(status, label)
print("ECHECS:", sum(1 for status, label in results if status.strip() == "FAIL"))

frame.Destroy()
sys.exit(0)
