"""Cue sheets et contenu des rapports d'erreur."""

import os
import tempfile
import unittest

from tests.helpers import REPO_ROOT  # noqa: F401  (met le dépôt dans sys.path)

from core.cue import _cue_stem, finalize_tracks, parse_cue_text, resolve_cue_audio
from core.error_report import build_error_report_message

SINGLE_FILE_CUE = """REM GENRE Hip-Hop
REM DATE 2000
PERFORMER "Caparezza"
TITLE "CapaRezza!"
FILE "Caparezza - CapaRezza!.flac" WAVE
  TRACK 01 AUDIO
    TITLE "Intro"
    INDEX 01 00:00:00
  TRACK 02 AUDIO
    TITLE "Deuxieme"
    INDEX 01 02:30:37
"""

MULTI_FILE_CUE = """TITLE "Album deja decoupe"
FILE "01 - piste.mp3" MP3
  TRACK 01 AUDIO
    INDEX 01 00:00:00
FILE "02 - piste.mp3" MP3
  TRACK 02 AUDIO
    INDEX 01 00:00:00
"""


class CueParsingTests(unittest.TestCase):
    def test_single_file_cue_is_parsed(self):
        sheet = parse_cue_text(SINGLE_FILE_CUE)

        self.assertFalse(sheet.multi_file)
        self.assertEqual(sheet.album, "CapaRezza!")
        self.assertEqual(sheet.album_performer, "Caparezza")
        self.assertEqual(sheet.date, "2000")
        self.assertEqual([track.title for track in sheet.tracks], ["Intro", "Deuxieme"])
        # 02:30:37 = 2 min 30 s + 37 cadres (75/s).
        self.assertEqual(sheet.tracks[1].start_ms, 150493)

    def test_multi_file_cue_is_flagged(self):
        self.assertTrue(parse_cue_text(MULTI_FILE_CUE).multi_file)

    def test_track_ends_chain_to_the_next_start(self):
        sheet = parse_cue_text(SINGLE_FILE_CUE)

        finalize_tracks(sheet.tracks, 300000)

        self.assertEqual(sheet.tracks[0].end_ms, sheet.tracks[1].start_ms)
        self.assertEqual(sheet.tracks[1].end_ms, 300000)


class CueAudioResolutionTests(unittest.TestCase):
    """Bug terrain : cue nommé « Album.cue.cue » (double extension)."""

    def test_cue_stem_strips_every_cue_extension(self):
        self.assertEqual(_cue_stem(r"d:\x\Caparezza - CapaRezza!.cue.cue"), "Caparezza - CapaRezza!")
        self.assertEqual(_cue_stem(r"d:\x\Album.cue"), "Album")

    def test_double_extension_cue_finds_its_audio_image(self):
        with tempfile.TemporaryDirectory() as folder:
            cue_path = os.path.join(folder, "Album.cue.cue")
            audio_path = os.path.join(folder, "Album.flac")
            open(cue_path, "w").close()
            open(audio_path, "w").close()
            # Autre fichier audio présent : le repli « unique fichier du dossier »
            # ne peut pas sauver la mise, seule la correspondance de nom le peut.
            open(os.path.join(folder, "Autre.flac"), "w").close()

            resolved = resolve_cue_audio(cue_path, "introuvable.flac")

            self.assertEqual(resolved, os.path.abspath(audio_path))

    def test_missing_audio_image_returns_none(self):
        with tempfile.TemporaryDirectory() as folder:
            cue_path = os.path.join(folder, "Album.cue")
            open(cue_path, "w").close()
            open(os.path.join(folder, "a.flac"), "w").close()
            open(os.path.join(folder, "b.flac"), "w").close()

            self.assertIsNone(resolve_cue_audio(cue_path, "introuvable.flac"))


class ErrorReportBodyTests(unittest.TestCase):
    """Bug terrain : rapport reçu avec « (no output captured) » et rien d'autre."""

    def test_application_message_is_reported_when_ffmpeg_never_ran(self):
        message = build_error_report_message(
            r"d:\musique\Album.cue.cue", "aac", "", "",
            "Audio file referenced by the cue sheet not found: Album.flac",
        )

        self.assertIn("Application error message:", message)
        self.assertIn("Album.flac", message)
        self.assertIn("(no output captured)", message)

    def test_ffmpeg_output_is_still_reported(self):
        message = build_error_report_message(
            r"d:\films\film.mp4", "mp4", "Error opening output files", "mon commentaire"
        )

        self.assertIn("Error opening output files", message)
        self.assertIn("mon commentaire", message)
        self.assertNotIn("Application error message:", message)


if __name__ == "__main__":
    unittest.main()
