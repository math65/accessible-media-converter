"""Bugs trouvés par l'audit complet de septembre 2026.

1. Contrôle de troncature (v1.20.5) : chaque flux de sortie était comparé à la
   plus LONGUE piste source du même type. Un fichier gardant une piste audio
   courte à côté d'une complète — exactement ceux que l'app signale « Son
   incomplet » au chargement — échouait donc à coup sûr.
2. Re-tag sur place : retirer ou remplacer la pochette d'un film faisait
   `-map -0:v`, qui emportait la piste vidéo ; l'original était remplacé.
3. Lot contenant un cue : les états s'affichaient sur la ligne d'indice égal
   au n° de JOB, alors qu'un album de N pistes donne N jobs pour une ligne.
"""

import os
import shutil
import tempfile
import types
import unittest

from tests.helpers import ffmpeg_available, probe_stream_types, run_ffmpeg

from core.batch_manager import BatchConversionManager
from core.conversion import ConversionTask
from core.cue import CueSheet, CueTrack
from core.formatting import normalize_format_settings
from core.metadata_retag import MetadataRetagTask
from core.probe import FileProber


@unittest.skipUnless(ffmpeg_available(), "FFmpeg embarqué absent")
class ShortSourceTrackTests(unittest.TestCase):
    """Une piste courte DANS LA SOURCE n'est pas un échec de conversion."""

    @classmethod
    def setUpClass(cls):
        cls.workdir = tempfile.mkdtemp(prefix="amc_audit_")
        cls.source = os.path.join(cls.workdir, "two_audio.mp4")
        run_ffmpeg([
            "-f", "lavfi", "-i", "testsrc=d=60:s=64x48:r=5",
            "-f", "lavfi", "-i", "sine=d=60",
            "-f", "lavfi", "-i", "sine=f=880:d=5",
            "-map", "0", "-map", "1", "-map", "2",
            "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", cls.source,
        ])

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.workdir, ignore_errors=True)

    def _convert(self, target_format, meta=None, **overrides):
        settings = normalize_format_settings(target_format, {})
        settings.update(overrides)
        output = os.path.join(self.workdir, f"out.{target_format}")
        meta = meta or FileProber().analyze(self.source)
        ConversionTask(meta, target_format, settings, output_path=output).run()
        return output

    def test_short_track_is_flagged_at_load(self):
        self.assertEqual(len(FileProber().analyze(self.source).short_audio_tracks), 1)

    def test_video_outputs_keep_both_tracks(self):
        for target_format in ("mkv", "mp4"):
            with self.subTest(target_format=target_format):
                output = self._convert(target_format, video_mode="copy")
                self.assertEqual(probe_stream_types(output), ["video", "audio", "audio"])

    def test_extracting_the_short_track(self):
        meta = FileProber().analyze(self.source)
        short = meta.audio_tracks[1]
        meta.audio_extract_track = {"original_index": short.index}
        self._convert("mp3", meta=meta)

    def test_extracting_the_full_track_still_checks_it(self):
        """Référence = la piste choisie, pas la plus courte : le contrôle reste actif."""
        meta = FileProber().analyze(self.source)
        task = ConversionTask(meta, "mp3", normalize_format_settings("mp3", {}))
        task._extract_source_index = meta.audio_tracks[0].index
        self.assertAlmostEqual(task._expected_duration_for_output(0, "audio"), 60, delta=0.5)


@unittest.skipUnless(ffmpeg_available(), "FFmpeg embarqué absent")
class InplaceCoverOnVideoTests(unittest.TestCase):
    def setUp(self):
        self.workdir = tempfile.mkdtemp(prefix="amc_audit_")
        self.cover = os.path.join(self.workdir, "cover.jpg")
        run_ffmpeg(["-f", "lavfi", "-i", "color=red:s=64x64", "-frames:v", "1", self.cover])

    def tearDown(self):
        shutil.rmtree(self.workdir, ignore_errors=True)

    def _film(self, name):
        path = os.path.join(self.workdir, name)
        run_ffmpeg([
            "-f", "lavfi", "-i", "testsrc=d=3:s=64x48:r=5", "-f", "lavfi", "-i", "sine=d=3",
            "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", path,
        ])
        return path

    def _retag(self, path, cover):
        meta = FileProber().analyze(path)
        MetadataRetagTask(meta, {"tags": {"title": "x"}, "cover": cover}).run()

    def test_remove_cover_keeps_the_film(self):
        path = self._film("film.mp4")
        self._retag(path, {"action": "remove"})
        self.assertEqual(probe_stream_types(path), ["video", "audio"])

    def test_replace_cover_keeps_the_film(self):
        path = self._film("film.mp4")
        self._retag(path, {"action": "replace", "path": self.cover})
        self.assertEqual(probe_stream_types(path), ["video", "audio", "video"])
        meta = FileProber().analyze(path)
        self.assertEqual(len(meta.video_tracks), 1)
        self.assertTrue(meta.has_cover_art)

    def test_remove_cover_on_audio_still_removes_it(self):
        path = os.path.join(self.workdir, "song.mp3")
        run_ffmpeg([
            "-f", "lavfi", "-i", "sine=d=3", "-i", self.cover,
            "-map", "0", "-map", "1", "-c:a", "libmp3lame", "-c:v", "copy",
            "-disposition:v:0", "attached_pic", path,
        ])
        self.assertTrue(FileProber().analyze(path).has_cover_art)
        self._retag(path, {"action": "remove"})
        self.assertEqual(probe_stream_types(path), ["audio"])


class CueJobRowTests(unittest.TestCase):
    def test_jobs_point_at_their_list_row(self):
        workdir = tempfile.mkdtemp(prefix="amc_audit_")
        try:
            sheet = CueSheet(album="Album", audio_ref=os.path.join(workdir, "album.flac"))
            sheet.tracks = [
                CueTrack(number=n, title=f"T{n}", start_ms=(n - 1) * 1000, end_ms=n * 1000)
                for n in (1, 2, 3)
            ]
            album = types.SimpleNamespace(
                full_path=os.path.join(workdir, "album.cue"), duration=3.0, cue_sheet=sheet,
                cue_error=None, output_override=None, relative_dir="",
            )
            single = types.SimpleNamespace(
                full_path=os.path.join(workdir, "single.flac"), duration=3.0, cue_sheet=None,
                output_override=None, relative_dir="",
            )
            manager = BatchConversionManager([album, single], "mp3", {})
            self.assertEqual([job.row for job in manager.jobs], [0, 0, 0, 1])
            self.assertEqual([job.cue_track for job in manager.jobs], [(1, 3), (2, 3), (3, 3), None])
            event = manager._build_job_event(manager.jobs[3])
            self.assertEqual((event["index"], event["row"]), (3, 1))
        finally:
            shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
