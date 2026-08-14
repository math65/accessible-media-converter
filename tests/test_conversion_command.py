"""Construction des commandes FFmpeg (sans exécution)."""

import unittest

from tests.helpers import (
    audio_track,
    make_media,
    mapped_streams,
    subtitle_track,
    video_track,
)

from core.conversion import ConversionTask
from core.ffmpeg_helpers import broadcast_input_args
from core.track_settings import build_default_track_settings

COPY_SETTINGS = {"video_mode": "copy", "audio_mode": "copy", "ffmpeg_threads": "auto"}


class VideoMappingTests(unittest.TestCase):
    def test_stale_config_never_maps_a_missing_stream(self):
        """Garde de dernier recours : même avec une config périmée en mémoire,
        aucun `-map` ne doit pointer vers un flux absent du fichier."""
        reference = make_media(
            video=[video_track(0)],
            audio=[audio_track(1), audio_track(2), audio_track(3)],
            subtitle=[subtitle_track(4)],
        )
        target = make_media(video=[video_track(0)], audio=[audio_track(1)])
        target.track_settings = build_default_track_settings(reference)

        cmd = []
        ConversionTask(target, "mp4", COPY_SETTINGS)._apply_video_container_track_mapping(cmd)

        self.assertEqual(mapped_streams(cmd), ["0:0", "0:1"])

    def test_unreadable_audio_stream_is_not_mapped(self):
        meta = make_media(
            video=[video_track(4)],
            audio=[audio_track(5), audio_track(6), audio_track(8, sample_rate=None)],
        )

        cmd = []
        ConversionTask(meta, "mp4", COPY_SETTINGS)._apply_video_container_track_mapping(cmd)

        self.assertEqual(mapped_streams(cmd), ["0:4", "0:5", "0:6"])

    def test_incompatible_subtitles_are_dropped_for_mp4(self):
        meta = make_media(
            video=[video_track(0)],
            audio=[audio_track(1)],
            subtitle=[subtitle_track(2, "dvb_teletext"), subtitle_track(3, "subrip")],
        )

        cmd = []
        ConversionTask(meta, "mp4", COPY_SETTINGS)._apply_video_container_track_mapping(cmd)

        self.assertEqual(mapped_streams(cmd), ["0:0", "0:1", "0:3"])

    def test_no_video_track_left_raises(self):
        meta = make_media(video=[video_track(0)], audio=[audio_track(1)])
        meta.track_settings = {
            "video_tracks": [{"original_index": 0, "keep": False, "dispositions": {}}],
            "audio_tracks": [{"original_index": 1, "keep": True, "dispositions": {}}],
            "subtitle_tracks": [],
        }

        with self.assertRaises(Exception):
            ConversionTask(meta, "mp4", COPY_SETTINGS)._apply_video_container_track_mapping([])


class BroadcastInputTests(unittest.TestCase):
    """Captures TV : PTS régénérés et analyse d'entrée élargie."""

    def test_broadcast_containers_get_repair_options(self):
        for path in (r"d:\tv\capture.mpg", r"d:\tv\capture.ts", r"d:\tv\dvd.vob", r"d:\tv\cam.m2ts"):
            with self.subTest(path=path):
                args = broadcast_input_args(path)
                self.assertIn("+genpts", args)
                self.assertIn("-probesize", args)
                self.assertIn("-analyzeduration", args)

    def test_regular_containers_are_untouched(self):
        for path in (r"d:\films\film.mp4", r"d:\musique\chanson.mp3", r"d:\films\serie.mkv"):
            with self.subTest(path=path):
                self.assertEqual(broadcast_input_args(path), [])


if __name__ == "__main__":
    unittest.main()
