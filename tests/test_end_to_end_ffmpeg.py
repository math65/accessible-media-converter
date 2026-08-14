"""Conversions réelles avec le FFmpeg embarqué (fixtures générées à la volée).

Ces tests reproduisent les scénarios terrain qui ont fait échouer des conversions
en v1.20.0. Ils sont ignorés si `bin/ffmpeg.exe` est absent.
"""

import copy
import os
import shutil
import tempfile
import unittest

from tests.helpers import (
    ffmpeg_available,
    probe_stream_types,
    probe_tags,
    run_ffmpeg,
)

from core.batch_manager import BatchConversionManager, JOB_STATE_DONE
from core.conversion import ConversionTask
from core.probe import FileProber
from core.track_settings import build_default_track_settings

LAVFI_VIDEO = ['-f', 'lavfi', '-i', 'testsrc=d=3:s=320x240']
COPY_SETTINGS = {"video_mode": "copy", "audio_mode": "copy", "ffmpeg_threads": "auto"}
MP3_SETTINGS = {
    "audio_mode": "convert", "rate_mode": "cbr", "audio_bitrate": "128k",
    "audio_sample_rate": "original", "audio_channels": "original", "ffmpeg_threads": "auto",
}

CUE_TEMPLATE = """PERFORMER "Artiste Test"
TITLE "Album Test"
FILE "{audio_name}" WAVE
  TRACK 01 AUDIO
    TITLE "Premiere"
    INDEX 01 00:00:00
  TRACK 02 AUDIO
    TITLE "Deuxieme"
    INDEX 01 00:03:00
"""


def sine(frequency, duration=3):
    return ['-f', 'lavfi', '-i', f'sine=f={frequency}:d={duration}']


@unittest.skipUnless(ffmpeg_available(), "FFmpeg embarqué absent de bin/")
class RealConversionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.mkdtemp(prefix="amc-tests-")

        # Référence : 1 vidéo + 3 audio + 1 sous-titre. Cible : 1 vidéo + 2 audio.
        cls.reference = os.path.join(cls.folder, "reference.mkv")
        subtitle = os.path.join(cls.folder, "sub.srt")
        with open(subtitle, "w", encoding="utf-8") as handle:
            handle.write("1\n00:00:00,000 --> 00:00:02,000\nbonjour\n")
        run_ffmpeg(
            LAVFI_VIDEO + sine(440) + sine(880) + sine(220) + ['-i', subtitle]
            + ['-map', '0:v', '-map', '1:a', '-map', '2:a', '-map', '3:a', '-map', '4:s', cls.reference]
        )

        cls.target = os.path.join(cls.folder, "target.mkv")
        run_ffmpeg(LAVFI_VIDEO + sine(440) + sine(880) + ['-map', '0:v', '-map', '1:a', '-map', '2:a', cls.target])

        # Capture façon flux de diffusion.
        cls.transport = os.path.join(cls.folder, "capture.ts")
        run_ffmpeg(
            LAVFI_VIDEO + sine(440)
            + ['-map', '0:v', '-map', '1:a', '-c:v', 'libx264', '-preset', 'ultrafast',
               '-c:a', 'aac', '-f', 'mpegts', cls.transport]
        )

        # Image album + cue sheet à double extension.
        cls.album_audio = os.path.join(cls.folder, "Album Test.wav")
        run_ffmpeg(['-f', 'lavfi', '-i', 'sine=f=440:d=6', cls.album_audio])
        cls.cue_path = os.path.join(cls.folder, "Album Test.cue.cue")
        with open(cls.cue_path, "w", encoding="utf-8") as handle:
            handle.write(CUE_TEMPLATE.format(audio_name="introuvable.wav"))

        cls.prober = FileProber()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.folder, ignore_errors=True)

    def output(self, name):
        return os.path.join(self.folder, name)

    def test_batch_track_config_applied_to_a_shorter_file(self):
        """Scénario du rapport « Infiltration 2022.mp4 » : la config de pistes
        d'un fichier plus riche est appliquée à un fichier qui a moins de flux."""
        reference_meta = self.prober.analyze(self.reference)
        target_meta = self.prober.analyze(self.target)
        target_meta.track_settings = copy.deepcopy(build_default_track_settings(reference_meta))

        output_path = self.output("depuis-config-lot.mp4")
        ConversionTask(target_meta, "mp4", COPY_SETTINGS, output_path=output_path).run()

        self.assertTrue(os.path.isfile(output_path))
        self.assertEqual(probe_stream_types(output_path), ["video", "audio", "audio"])

    def test_transport_stream_converts_to_mp4(self):
        meta = self.prober.analyze(self.transport)

        output_path = self.output("capture.mp4")
        task = ConversionTask(meta, "mp4", COPY_SETTINGS, output_path=output_path)
        task.run()

        self.assertIn("+genpts", task.last_command)
        self.assertIn("-probesize", task.last_command)
        self.assertEqual(probe_stream_types(output_path), ["video", "audio"])

    def test_cue_sheet_with_double_extension_splits_into_tracks(self):
        """Le cue référence un fichier absent : la résolution doit retomber sur
        le nom du cue débarrassé de ses deux extensions."""
        meta = self.prober.analyze(self.cue_path)
        self.assertIsNone(meta.cue_error)
        self.assertEqual(len(meta.cue_sheet.tracks), 2)

        manager = BatchConversionManager([meta], "mp3", MP3_SETTINGS, max_concurrent=2)
        manager.start().join(timeout=180)

        self.assertEqual([job.state for job in manager.jobs], [JOB_STATE_DONE, JOB_STATE_DONE])
        album_dir = os.path.join(self.folder, "Album Test")
        self.assertEqual(
            sorted(os.listdir(album_dir)), ["01 - Premiere.mp3", "02 - Deuxieme.mp3"]
        )
        tags = probe_tags(os.path.join(album_dir, "02 - Deuxieme.mp3"))
        self.assertEqual(tags.get("title"), "Deuxieme")
        self.assertEqual(tags.get("album"), "Album Test")


if __name__ == "__main__":
    unittest.main()
