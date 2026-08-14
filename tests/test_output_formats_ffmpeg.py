"""Chaque format de sortie converti pour de vrai avec le FFmpeg embarqué.

Filet pour les montées de version de FFmpeg : une option retirée en amont
(l'app en émet une quarantaine) casserait un format sans prévenir. Le test passe
par les vrais chemins de code, donc ce sont les options réellement émises par
l'application qui sont exercées.

Écrit lors du passage FFmpeg 8.1.2 -> 9.0.1 (v1.20.1).
"""

import os
import shutil
import tempfile
import unittest

from tests.helpers import ffmpeg_available, run_ffmpeg

from core.conversion import ConversionTask, get_output_extension
from core.merge import MergeTask
from core.probe import FileProber

BASE_AUDIO = {
    "audio_mode": "convert", "audio_sample_rate": "original",
    "audio_channels": "original", "ffmpeg_threads": "auto",
}
COPY = {"audio_mode": "copy", "video_mode": "copy", "ffmpeg_threads": "auto"}


@unittest.skipUnless(ffmpeg_available(), "FFmpeg embarqué absent de bin/")
class OutputFormatTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.mkdtemp(prefix="amc-formats-")
        cls.prober = FileProber()

        cls.audio = os.path.join(cls.folder, "son.wav")
        run_ffmpeg(['-f', 'lavfi', '-i', 'sine=f=440:d=1', cls.audio])
        cls.audio2 = os.path.join(cls.folder, "son2.wav")
        run_ffmpeg(['-f', 'lavfi', '-i', 'sine=f=660:d=1', cls.audio2])
        cls.video = os.path.join(cls.folder, "film.mkv")
        run_ffmpeg([
            '-f', 'lavfi', '-i', 'testsrc=d=1:s=192x144', '-f', 'lavfi', '-i', 'sine=f=440:d=1',
            '-map', '0:v', '-map', '1:a', cls.video,
        ])
        cls.image = os.path.join(cls.folder, "photo.png")
        run_ffmpeg(['-f', 'lavfi', '-i', 'testsrc=d=1:s=192x144', '-frames:v', '1', cls.image])
        cls.transport = os.path.join(cls.folder, "capture.ts")
        run_ffmpeg([
            '-f', 'lavfi', '-i', 'testsrc=d=1:s=192x144', '-f', 'lavfi', '-i', 'sine=f=440:d=1',
            '-map', '0:v', '-map', '1:a', '-c:v', 'libx264', '-preset', 'ultrafast',
            '-c:a', 'aac', '-f', 'mpegts', cls.transport,
        ])

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.folder, ignore_errors=True)

    def convert(self, label, source, target_format, settings):
        meta = self.prober.analyze(source)
        output = os.path.join(self.folder, f"{label}.{get_output_extension(target_format)}")
        ConversionTask(meta, target_format, settings, output_path=output).run()
        self.assertTrue(os.path.isfile(output), label)
        self.assertGreater(os.path.getsize(output), 0, label)

    def test_audio_formats(self):
        cases = [
            ("mp3_cbr", "mp3", {"rate_mode": "cbr", "audio_bitrate": "192k"}),
            ("mp3_abr", "mp3", {"rate_mode": "abr", "audio_bitrate": "192k"}),
            ("mp3_vbr", "mp3", {"rate_mode": "vbr", "audio_qscale": 2}),
            ("aac_cbr", "aac", {"rate_mode": "cbr", "audio_bitrate": "192k"}),
            ("aac_vbr", "aac", {"rate_mode": "vbr", "audio_qscale": 3}),
            ("flac16", "flac", {"flac_compression": 5, "audio_bit_depth": "16"}),
            ("flac24", "flac", {"flac_compression": 8, "audio_bit_depth": "24"}),
            ("alac24", "alac", {"audio_bit_depth": "24"}),
            ("wav24", "wav", {"audio_bit_depth": "24"}),
            ("opus", "opus", {"audio_bitrate": "128k"}),
            ("ogg", "ogg", {"audio_qscale": 6}),
            ("wma", "wma", {"audio_bitrate": "128k"}),
            ("m4b", "m4b", {"rate_mode": "cbr", "audio_bitrate": "128k"}),
            ("mono44k", "mp3", {"rate_mode": "cbr", "audio_bitrate": "128k",
                                "audio_channels": "1", "audio_sample_rate": "44100"}),
            ("loudnorm", "mp3", {"rate_mode": "cbr", "audio_bitrate": "192k",
                                 "audio_normalize_streaming": True}),
        ]
        for label, target_format, extra in cases:
            with self.subTest(format=label):
                self.convert(label, self.audio, target_format, {**BASE_AUDIO, **extra})

    def test_video_formats(self):
        encode = {
            **BASE_AUDIO, "rate_mode": "cbr", "audio_bitrate": "128k", "video_mode": "convert",
            "video_crf": 23, "video_encoder_preset": "ultrafast",
            "video_pixel_format": "yuv420p", "video_profile": "high",
        }
        cases = [
            ("mp4_encode", self.video, "mp4", encode),
            ("mp4_copy", self.video, "mp4", COPY),
            ("mkv_copy", self.video, "mkv", COPY),
            ("mov_copy", self.video, "mov", COPY),
            ("ts_to_mp4", self.transport, "mp4", COPY),
            ("video_to_mp3", self.video, "mp3",
             {**BASE_AUDIO, "rate_mode": "cbr", "audio_bitrate": "192k"}),
        ]
        for label, source, target_format, settings in cases:
            with self.subTest(format=label):
                self.convert(label, source, target_format, settings)

    def test_image_formats(self):
        cases = [
            ("jpeg", "jpeg", {"image_quality": 85}),
            ("png", "png", {"image_compression": 6}),
            ("webp_lossy", "webp", {"image_quality": 80}),
            ("webp_lossless", "webp", {"image_lossless": True}),
            ("tiff_raw", "tiff", {"image_compression": "raw"}),
            ("tiff_lzw", "tiff", {"image_compression": "lzw"}),
            ("bmp", "bmp", {}),
            ("resize", "jpeg", {"image_quality": 85, "image_resize": "96x72"}),
        ]
        for label, target_format, extra in cases:
            with self.subTest(format=label):
                self.convert(label, self.image, target_format, {"ffmpeg_threads": "auto", **extra})

    def test_merge_formats(self):
        cases = [
            ("merge_mp3", "mp3", {"rate_mode": "cbr", "audio_bitrate": "192k"}),
            ("merge_m4b", "m4b", {"rate_mode": "cbr", "audio_bitrate": "128k"}),
        ]
        for label, target_format, extra in cases:
            with self.subTest(format=label):
                metas = [self.prober.analyze(self.audio), self.prober.analyze(self.audio2)]
                output = os.path.join(self.folder, f"{label}.{get_output_extension(target_format)}")
                MergeTask(metas, target_format, {**BASE_AUDIO, **extra}, output_path=output).run()
                self.assertGreater(os.path.getsize(output), 0, label)


if __name__ == "__main__":
    unittest.main()
