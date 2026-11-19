"""Rapports automatiques d'octobre-novembre 2026 sur v1.20.6.

- 2026-10-22 : extraction MP3 d'une capture France 3 (.ts) en « 96 kHz ».
  libmp3lame plafonne à 48 kHz : « Specified sample rate 96000 is not
  supported », code -22, aucune sortie. La boîte de réglages proposait 96 kHz
  à tous les formats.
- 2026-11-05 : extraction MP3 d'un MKV vers un disque M: plein. Code
  4294967268 (= -28, ENOSPC) affiché tel quel, et formulaire de rapport ouvert
  alors que l'app n'y est pour rien.
"""

import os
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

from tests.helpers import ffmpeg_available, run_ffmpeg

from core.batch_manager import JOB_STATE_ERROR, BatchConversionManager
from core.conversion import ConversionTask
from core.ffmpeg_helpers import (
    DiskFullError,
    apply_common_audio_options,
    disk_full_error,
    ffmpeg_error_code,
    get_ffprobe_path,
    is_disk_full_failure,
    is_sample_rate_supported,
    resolve_sample_rate,
)
from core.formatting import normalize_format_settings
from core.probe import FileProber


class SampleRateTests(unittest.TestCase):
    def test_mp3_and_wma_stop_at_48k(self):
        self.assertFalse(is_sample_rate_supported('mp3', '96000'))
        self.assertFalse(is_sample_rate_supported('wma', '96000'))
        self.assertTrue(is_sample_rate_supported('mp3', '44100'))

    def test_opus_has_no_44k(self):
        self.assertFalse(is_sample_rate_supported('opus', '44100'))
        self.assertFalse(is_sample_rate_supported('opus', '22050'))
        self.assertTrue(is_sample_rate_supported('opus', '48000'))

    def test_other_encoders_take_everything_offered(self):
        for codec in ('aac', 'flac', 'alac', 'wav', 'ogg'):
            for rate in ('22050', '44100', '48000', '96000'):
                self.assertTrue(is_sample_rate_supported(codec, rate), (codec, rate))

    def test_original_is_always_fine(self):
        self.assertTrue(is_sample_rate_supported('opus', 'original'))
        self.assertIsNone(resolve_sample_rate('mp3', 'original'))

    def test_refused_rate_becomes_the_nearest_accepted(self):
        self.assertEqual(resolve_sample_rate('mp3', '96000'), '48000')
        self.assertEqual(resolve_sample_rate('opus', '44100'), '48000')
        self.assertEqual(resolve_sample_rate('opus', '22050'), '24000')
        self.assertEqual(resolve_sample_rate('aac', '96000'), '96000')

    def test_command_gets_the_corrected_rate(self):
        cmd = []
        apply_common_audio_options(cmd, {'audio_sample_rate': '96000'}, 'mp3')
        self.assertEqual(cmd, ['-ar', '48000'])
        cmd = []
        apply_common_audio_options(cmd, {'audio_sample_rate': '96000'})
        self.assertEqual(cmd, ['-ar', '96000'])


class DiskFullTests(unittest.TestCase):
    def test_windows_unsigned_code_is_read_back(self):
        self.assertEqual(ffmpeg_error_code(4294967268), -28)
        self.assertEqual(ffmpeg_error_code(4294967274), -22)
        self.assertEqual(ffmpeg_error_code(1), 1)
        self.assertIsNone(ffmpeg_error_code(None))

    def test_field_code_means_disk_full(self):
        self.assertTrue(is_disk_full_failure(4294967268, []))

    def test_stderr_message_means_disk_full(self):
        line = "[out#0/mp3 @ 000] Error writing trailer: No space left on device"
        self.assertTrue(is_disk_full_failure(1, [line]))

    def test_other_failures_are_not_disk_full(self):
        self.assertFalse(is_disk_full_failure(4294967274, ["Invalid argument"]))

    def test_message_names_the_drive(self):
        error = disk_full_error(r"M:\Films\film.mp3")
        self.assertIsInstance(error, DiskFullError)
        self.assertIn("M:", str(error))

    def test_batch_marks_the_job_as_disk_full(self):
        """Le lot classe l'échec à part : l'UI n'ouvre alors pas le rapport."""
        workdir = tempfile.mkdtemp(prefix="amc_diskfull_")
        self.addCleanup(shutil.rmtree, workdir, ignore_errors=True)
        source = os.path.join(workdir, "film.mkv")
        open(source, "wb").close()

        class _Meta:
            full_path = source
            duration = 60.0
            cue_sheet = None
            output_override = None
            relative_dir = ""

        def failing_run(task, *args, **kwargs):
            raise disk_full_error(os.path.join(workdir, "film.mp3"))

        with mock.patch.object(ConversionTask, "run", failing_run):
            manager = BatchConversionManager([_Meta()], "mp3", {}, max_concurrent=1)
            manager.start().join(timeout=30)
        job = manager.jobs[0]
        self.assertEqual(job.state, JOB_STATE_ERROR)
        self.assertEqual(job.error_kind, "disk_full")
        self.assertEqual(manager._build_job_event(job)["error_kind"], "disk_full")


@unittest.skipUnless(ffmpeg_available(), "FFmpeg embarqué absent (bin/ffmpeg.exe)")
class SampleRateEndToEndTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="amc_rate_")
        cls.source = os.path.join(cls.tmp, "capture.ts")
        run_ffmpeg([
            "-f", "lavfi", "-i", "testsrc=size=160x120:rate=25:duration=8",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=8:sample_rate=48000",
            "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-shortest",
            "-f", "mpegts", cls.source,
        ])

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _sample_rate(self, path, stream="a:0"):
        return subprocess.run(
            [get_ffprobe_path(), "-v", "error", "-select_streams", stream,
             "-show_entries", "stream=sample_rate", "-of", "default=nw=1:nk=1", path],
            capture_output=True, text=True, timeout=60,
        ).stdout.strip()

    def test_field_case_mp3_at_96k_with_loudnorm(self):
        """La commande exacte du rapport : MP3, 96 kHz, normalisation streaming."""
        settings = normalize_format_settings("mp3", {
            "audio_sample_rate": "96000", "audio_normalize_streaming": True,
        })
        settings["ffmpeg_threads"] = "auto"
        output = os.path.join(self.tmp, "capture.mp3")
        ConversionTask(FileProber().analyze(self.source), "mp3", settings, output_path=output).run()
        self.assertEqual(self._sample_rate(output), "48000")

    def test_mkv_opus_at_44k(self):
        settings = normalize_format_settings("mkv", {
            "audio_codec": "opus", "audio_sample_rate": "44100",
        })
        settings["ffmpeg_threads"] = "auto"
        output = os.path.join(self.tmp, "capture.mkv")
        ConversionTask(FileProber().analyze(self.source), "mkv", settings, output_path=output).run()
        self.assertEqual(self._sample_rate(output), "48000")


if __name__ == "__main__":
    unittest.main()
