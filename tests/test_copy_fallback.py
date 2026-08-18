"""Copie de flux refusée par le conteneur de sortie.

Rapport terrain (2026-08-18, v1.20.1) : un lot de 215 AVI convertis en MP4 avec
« Copier le flux (avancé) ». Leur vidéo est du msmpeg4v3 (DivX 3), que le muxeur
MP4 ne sait pas étiqueter : il refuse d'écrire l'en-tête et TOUT le fichier
échoue (« Could not find tag for codec msmpeg4v3 in stream #0 »). La conversion
est désormais relancée en réencodant le flux fautif.
"""

import os
import shutil
import tempfile
import unittest

from tests.helpers import ffmpeg_available, probe_stream_types, run_ffmpeg

from core.batch_manager import (
    JOB_STATE_DONE,
    NOTICE_COPY_REENCODED,
    BatchConversionManager,
)
from core.conversion import ConversionTask
from core.ffmpeg_helpers import detect_uncopyable_streams
from core.merge import MergeTask
from core.probe import FileProber

MUXER_REFUSAL = (
    "[mp4 @ 000001b4bc9a22c0] Could not find tag for codec msmpeg4v3 in stream #0, "
    "codec not currently supported in container"
)

COPY_SETTINGS = {"video_mode": "copy", "audio_mode": "copy", "ffmpeg_threads": "auto"}


class FakeTrack:
    def __init__(self, codec_name):
        self.codec_name = codec_name


class FakeMeta:
    def __init__(self, video, audio):
        self.video_codec = video
        self.audio_codec = audio
        self.video_tracks = [FakeTrack(video)] if video else []
        self.audio_tracks = [FakeTrack(audio)] if audio else []


class DetectionTests(unittest.TestCase):
    """La détection ne doit réencoder que le flux réellement refusé."""

    def setUp(self):
        self.meta = FakeMeta("msmpeg4v3", "mp3")

    def test_video_codec_refused(self):
        self.assertEqual(
            detect_uncopyable_streams([MUXER_REFUSAL], [self.meta], {"video", "audio"}),
            {"video"},
        )

    def test_audio_codec_refused(self):
        line = "[mp4 @ 0] Could not find tag for codec dts in stream #1, codec not currently supported in container"
        self.assertEqual(
            detect_uncopyable_streams([line], [FakeMeta("h264", "dts")], {"video", "audio"}),
            {"audio"},
        )

    def test_only_streams_actually_copied_are_retried(self):
        """L'audio était déjà réencodé : rien à changer de ce côté."""
        self.assertEqual(
            detect_uncopyable_streams([MUXER_REFUSAL], [self.meta], {"video"}), {"video"}
        )
        self.assertEqual(
            detect_uncopyable_streams([MUXER_REFUSAL], [self.meta], {"audio"}), set()
        )

    def test_unknown_codec_falls_back_to_every_copied_stream(self):
        line = "[mp4 @ 0] Could not find tag for codec inconnu in stream #0"
        self.assertEqual(
            detect_uncopyable_streams([line], [self.meta], {"video", "audio"}),
            {"video", "audio"},
        )

    def test_no_metadata_falls_back_to_every_copied_stream(self):
        self.assertEqual(
            detect_uncopyable_streams([MUXER_REFUSAL], [None], {"video"}), {"video"}
        )

    def test_other_failures_are_not_retried(self):
        lines = ["[out#0/mp4 @ 0] Could not write header (incorrect codec parameters ?)"]
        self.assertEqual(detect_uncopyable_streams(lines, [self.meta], {"video"}), set())

    def test_nothing_copied_means_nothing_to_retry(self):
        self.assertEqual(detect_uncopyable_streams([MUXER_REFUSAL], [self.meta], set()), set())


@unittest.skipUnless(ffmpeg_available(), "FFmpeg embarqué absent de bin/")
class RealCopyFallbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.mkdtemp(prefix="amc-copyfallback-")
        # AVI DivX 3 (msmpeg4v3) + MP3 : la source du rapport terrain.
        cls.divx = os.path.join(cls.folder, "Mission evasion.avi")
        run_ffmpeg(
            ['-f', 'lavfi', '-i', 'testsrc=d=2:s=320x240', '-f', 'lavfi', '-i', 'sine=f=440:d=2',
             '-c:v', 'msmpeg4', '-c:a', 'libmp3lame', cls.divx]
        )
        cls.divx2 = os.path.join(cls.folder, "Mission evasion 2.avi")
        shutil.copyfile(cls.divx, cls.divx2)
        # Témoin : du H.264 en MP4, parfaitement copiable vers du MP4.
        cls.h264 = os.path.join(cls.folder, "copiable.mp4")
        run_ffmpeg(
            ['-f', 'lavfi', '-i', 'testsrc=d=2:s=320x240', '-f', 'lavfi', '-i', 'sine=f=440:d=2',
             '-c:v', 'libx264', '-preset', 'ultrafast', '-c:a', 'aac', cls.h264]
        )
        cls.prober = FileProber()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.folder, ignore_errors=True)

    def output(self, name):
        return os.path.join(self.folder, name)

    def test_divx_avi_to_mp4_is_reencoded_instead_of_failing(self):
        meta = self.prober.analyze(self.divx)
        self.assertEqual(meta.video_codec, "msmpeg4v3")

        output_path = self.output("mission.mp4")
        task = ConversionTask(meta, "mp4", COPY_SETTINGS, output_path=output_path)
        task.run()

        self.assertEqual(task.copy_fallback_kinds, {"video"})
        self.assertIn("libx264", task.last_command)
        self.assertEqual(probe_stream_types(output_path), ["video", "audio"])

    def test_copiable_source_is_still_copied(self):
        """Pas de réencodage abusif : le H.264 passe toujours en copie."""
        meta = self.prober.analyze(self.h264)

        output_path = self.output("temoin.mp4")
        task = ConversionTask(meta, "mp4", COPY_SETTINGS, output_path=output_path)
        task.run()

        self.assertEqual(task.copy_fallback_kinds, set())
        self.assertNotIn("libx264", task.last_command)
        self.assertEqual(probe_stream_types(output_path), ["video", "audio"])

    def test_batch_reports_the_reencoding(self):
        meta = self.prober.analyze(self.divx)
        meta.full_path = self.divx

        manager = BatchConversionManager(
            [meta], "mp4", COPY_SETTINGS, output_dir=self.output("lot"), max_concurrent=1
        )
        manager.start().join(timeout=180)

        job = manager.jobs[0]
        self.assertEqual(job.state, JOB_STATE_DONE)
        self.assertEqual(job.notice, NOTICE_COPY_REENCODED)

    def test_merge_falls_back_too(self):
        metas = [self.prober.analyze(self.divx), self.prober.analyze(self.divx2)]

        output_path = self.output("fusion.mp4")
        task = MergeTask(metas, "mp4", COPY_SETTINGS, output_path)
        task.run()

        self.assertEqual(task.copy_fallback_kinds, {"video"})
        self.assertEqual(probe_stream_types(output_path), ["video", "audio"])


if __name__ == "__main__":
    unittest.main()
