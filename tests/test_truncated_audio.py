"""Détection des pistes audio amputées, et robustesse de l'outil de rapport.

Contexte terrain (août 2026) : des MP4 dont la vidéo est complète mais dont
TOUTES les pistes audio s'arrêtent au bout de quelques secondes. La durée d'un
conteneur étant celle de son flux le plus long, ces fichiers paraissaient
intacts à tout contrôle global — y compris au filet anti-troncature d'AMC.
"""

import os
import shutil
import tempfile
import unittest

from tests.helpers import (
    audio_track,
    ffmpeg_available,
    make_media,
    run_ffmpeg,
    video_track,
)

from core.error_report import (
    _drop_stderr_echo,
    build_error_report_message,
    rerun_ffmpeg_verbose,
    summarize_ffmpeg_stderr,
)
from core.ffmpeg_helpers import get_ffmpeg_path
from core.probe import FileProber, find_short_tracks, parse_stream_duration


class ParseStreamDurationTests(unittest.TestCase):
    def test_reads_plain_duration(self):
        self.assertAlmostEqual(parse_stream_duration({'duration': '17.600000'}), 17.6)

    def test_falls_back_to_duration_ts_and_time_base(self):
        stream = {'duration_ts': 844800, 'time_base': '1/48000'}
        self.assertAlmostEqual(parse_stream_duration(stream), 17.6, places=3)

    def test_reads_matroska_duration_tag(self):
        """Matroska ne stocke aucune durée par piste : seul ce tag existe."""
        stream = {'tags': {'DURATION': '01:19:34.848000000'}}
        self.assertAlmostEqual(parse_stream_duration(stream), 4774.848, places=3)

    def test_unknown_duration_returns_none(self):
        self.assertIsNone(parse_stream_duration({'duration': 'N/A'}))
        self.assertIsNone(parse_stream_duration({}))
        self.assertIsNone(parse_stream_duration(None))

    def test_broken_time_base_is_survived(self):
        self.assertIsNone(parse_stream_duration({'duration_ts': 10, 'time_base': '1/0'}))


class FindShortTracksTests(unittest.TestCase):
    def _media(self, container, audio_durations):
        meta = make_media(
            video=[video_track(0)],
            audio=[audio_track(index + 1) for index in range(len(audio_durations))],
        )
        meta.duration = container
        for track, value in zip(meta.audio_tracks, audio_durations):
            track.duration = value
        meta.video_tracks[0].duration = container
        return meta

    def test_detects_the_field_case(self):
        """Merlin : 1 h 19 de conteneur, trois pistes audio à 17,6 s."""
        meta = self._media(4774.85, [17.6, 17.6, 17.51])
        self.assertEqual(len(find_short_tracks(meta)), 3)

    def test_healthy_file_is_not_flagged(self):
        meta = self._media(4774.85, [4774.85, 4770.0])
        self.assertEqual(find_short_tracks(meta), [])

    def test_slightly_shorter_track_is_not_flagged(self):
        """Une piste qui s'arrête un peu avant la fin reste légitime."""
        meta = self._media(3600.0, [3500.0])
        self.assertEqual(find_short_tracks(meta), [])

    def test_unknown_duration_is_never_flagged(self):
        """Sans mesure (Matroska sans tag), aucun soupçon."""
        meta = self._media(4774.85, [None])
        self.assertEqual(find_short_tracks(meta), [])

    def test_short_container_is_ignored(self):
        """Sur un jingle, le ratio n'a aucun sens."""
        meta = self._media(10.0, [1.0])
        self.assertEqual(find_short_tracks(meta), [])


class StderrSummaryTests(unittest.TestCase):
    def test_keeps_head_and_tail(self):
        """L'en-tête `Input #0 ... from '<chemin>'` doit survivre au découpage."""
        header = "Input #0, mov, from 'F:/film.mp4':"
        lines = [header] + ["L{0}".format(i) for i in range(300)]
        summary = summarize_ffmpeg_stderr(lines)
        self.assertIn(header, summary)
        self.assertIn("L299", summary)
        self.assertIn("lignes omises", summary)

    def test_short_output_is_untouched(self):
        self.assertEqual(summarize_ffmpeg_stderr(["a", "b", "c"]), "a\nb\nc")

    def test_empty_input(self):
        self.assertEqual(summarize_ffmpeg_stderr([]), "")

    def test_drops_stderr_echo_from_application_message(self):
        """Le `raise` colle le tail au message : le rapport le montrait 2 fois."""
        stderr = "frame= 12\nError muxing a packet"
        message = "Sortie anormalement courte.\nframe= 12\nError muxing a packet"
        self.assertEqual(
            _drop_stderr_echo(message, stderr), "Sortie anormalement courte."
        )

    def test_report_body_does_not_duplicate_stderr(self):
        stderr = "Error muxing a packet"
        body = build_error_report_message(
            "F:/film.mp4", "mp3", stderr,
            error_message="Sortie trop courte.\nError muxing a packet",
        )
        self.assertEqual(body.count("Error muxing a packet"), 1)

    def test_application_message_is_kept_when_not_an_echo(self):
        body = build_error_report_message(
            "F:/film.mp4", "mp3", "", error_message="This cue sheet cannot be split."
        )
        self.assertIn("This cue sheet cannot be split.", body)


class VerboseRerunTests(unittest.TestCase):
    """La re-passe de diagnostic ne doit jamais écrire chez l'utilisateur."""

    @unittest.skipUnless(ffmpeg_available(), "FFmpeg embarqué absent")
    def test_diagnostic_does_not_overwrite_user_output(self):
        work_dir = tempfile.mkdtemp(prefix='amc-test-')
        self.addCleanup(shutil.rmtree, work_dir, ignore_errors=True)
        source = os.path.join(work_dir, 'source.wav')
        output = os.path.join(work_dir, 'sortie.mp3')
        run_ffmpeg(['-f', 'lavfi', '-i', 'sine=frequency=440:duration=1', source])

        precious = 'fichier precieux de l utilisateur'
        with open(output, 'w', encoding='utf-8') as handle:
            handle.write(precious)

        rerun_ffmpeg_verbose([get_ffmpeg_path(), '-y', '-i', source, output])

        with open(output, encoding='utf-8') as handle:
            self.assertEqual(handle.read(), precious)

    def test_missing_command_is_survived(self):
        self.assertIn("No FFmpeg command", rerun_ffmpeg_verbose([]))


@unittest.skipUnless(ffmpeg_available(), "FFmpeg embarqué absent")
class TruncatedAudioEndToEndTests(unittest.TestCase):
    """Vraie conversion : un MP4 dont la vidéo dure 60 s et l'audio 5 s."""

    @classmethod
    def setUpClass(cls):
        cls.work_dir = tempfile.mkdtemp(prefix='amc-truncated-')
        cls.truncated = os.path.join(cls.work_dir, 'audio_ampute.mp4')
        cls.healthy = os.path.join(cls.work_dir, 'sain.mp4')
        # Sans -shortest, la sortie garde les 60 s de vidéo et n'a que 5 s d'audio.
        run_ffmpeg([
            '-f', 'lavfi', '-i', 'testsrc=size=160x120:rate=10:duration=60',
            '-f', 'lavfi', '-i', 'sine=frequency=440:duration=5',
            '-c:v', 'libx264', '-preset', 'ultrafast', '-c:a', 'aac', cls.truncated,
        ])
        run_ffmpeg([
            '-f', 'lavfi', '-i', 'testsrc=size=160x120:rate=10:duration=60',
            '-f', 'lavfi', '-i', 'sine=frequency=440:duration=60',
            '-c:v', 'libx264', '-preset', 'ultrafast', '-c:a', 'aac', cls.healthy,
        ])

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.work_dir, ignore_errors=True)

    def test_container_duration_hides_the_problem(self):
        """Le point de départ du bug : la durée globale ne montre rien."""
        meta = FileProber().analyze(self.truncated)
        self.assertAlmostEqual(meta.duration, 60.0, delta=1.0)

    def test_probe_flags_the_truncated_audio(self):
        meta = FileProber().analyze(self.truncated)
        self.assertEqual(len(meta.short_audio_tracks), 1)
        track, duration, container = meta.short_audio_tracks[0]
        self.assertAlmostEqual(duration, 5.0, delta=0.5)
        self.assertAlmostEqual(container, 60.0, delta=1.0)

    def test_healthy_file_is_not_flagged(self):
        meta = FileProber().analyze(self.healthy)
        self.assertEqual(meta.short_audio_tracks, [])

    def test_per_track_durations_are_captured(self):
        meta = FileProber().analyze(self.healthy)
        self.assertIsNotNone(meta.audio_tracks[0].duration)
        self.assertIsNotNone(meta.video_tracks[0].duration)


if __name__ == '__main__':
    unittest.main()
