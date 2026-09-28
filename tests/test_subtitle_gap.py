"""Sous-titres dont un silence dépasse ce que le conteneur MP4 sait écrire.

Contexte terrain (août 2026) : quatre films d'un utilisateur sortaient d'AMC
avec une vidéo complète et un son coupé au bout de quelques secondes, sans la
moindre erreur (FFmpeg terminait en code 0). Cause reproduite à l'identique sur
la source d'origine : une piste de sous-titres « forcés » ne portant que trois
répliques (12 s, 100 s, puis 4767 s). Le muxeur MP4 comble un silence entre deux
répliques par un échantillon vide dont la durée, comptée en microsecondes, ne
tient plus sur 32 bits — il le refuse, ET cesse d'écrire l'audio du fichier.
"""

import os
import shutil
import tempfile
import unittest

from tests.helpers import (
    audio_track,
    ffmpeg_available,
    make_media,
    mapped_streams,
    run_ffmpeg,
    subtitle_track,
    video_track,
)

from core.conversion import ConversionTask
from core.ffmpeg_helpers import (
    detect_oversized_subtitle_streams,
    parse_oversized_subtitle_stream,
)
from core.formatting import normalize_format_settings
from core.probe import FileProber

REFUS = "[mp4 @ 0000026b] Packet duration: 4662080000 / dts: 4766720000 in stream 4 is out of range"
SETTINGS = {"video_mode": "copy", "audio_mode": "convert", "ffmpeg_threads": "auto"}


def _task(target_format="mp4", **tracks):
    meta = make_media(
        video=[video_track(0)],
        audio=[audio_track(1), audio_track(2)],
        subtitle=[subtitle_track(3), subtitle_track(4)],
        **tracks,
    )
    return ConversionTask(meta, target_format, SETTINGS)


class RefusalMessageTests(unittest.TestCase):
    def test_reads_the_stream_index_from_the_muxer(self):
        self.assertEqual(parse_oversized_subtitle_stream(REFUS), 4)

    def test_ignores_unrelated_lines(self):
        self.assertIsNone(parse_oversized_subtitle_stream("frame=42 time=00:00:01.00"))
        self.assertIsNone(parse_oversized_subtitle_stream(""))

    def test_collects_every_refused_stream(self):
        lines = [REFUS, "frame=1", REFUS.replace("stream 4", "stream 5")]
        self.assertEqual(detect_oversized_subtitle_streams(lines), {4, 5})


class CulpritSelectionTests(unittest.TestCase):
    """La piste retirée est celle que FFmpeg a nommée, jamais une supposition."""

    def _mapped_task(self, target_format="mp4"):
        task = _task(target_format)
        task._apply_video_container_track_mapping([])
        return task

    def test_names_the_source_track_behind_the_output_index(self):
        task = self._mapped_task()
        task._oversized_subtitle_outputs = {3}  # 4e flux de sortie = sous-titre #3
        self.assertEqual(task._subtitle_streams_to_drop(set()), {3})

    def test_reads_the_message_from_the_captured_output_too(self):
        """Le message peut avoir été lu avant que le tampon ne tourne."""
        task = self._mapped_task()
        task.stderr_lines = [REFUS.replace("stream 4", "stream 3")]
        self.assertEqual(task._subtitle_streams_to_drop(set()), {3})

    def test_never_drops_a_track_already_dropped(self):
        task = self._mapped_task()
        task._oversized_subtitle_outputs = {3}
        self.assertEqual(task._subtitle_streams_to_drop({3}), set())

    def test_stays_silent_without_a_refusal(self):
        task = self._mapped_task()
        self.assertEqual(task._subtitle_streams_to_drop(set()), set())

    def test_never_drops_a_stream_that_is_not_a_subtitle(self):
        """Un index pointant sur l'audio ne doit rien déclencher : sans piste
        identifiée, l'échec remonte tel quel plutôt que de tenter au hasard."""
        task = self._mapped_task()
        task._oversized_subtitle_outputs = {1}
        self.assertEqual(task._subtitle_streams_to_drop(set()), set())

    def test_ignores_containers_that_do_not_use_tx3g(self):
        task = self._mapped_task("mkv")
        task._oversized_subtitle_outputs = {3}
        self.assertEqual(task._subtitle_streams_to_drop(set()), set())


class MappingExclusionTests(unittest.TestCase):
    def test_dropped_subtitle_is_not_mapped_and_the_rest_survives(self):
        cmd = []
        _task()._apply_video_container_track_mapping(cmd, drop_subtitles={3})
        self.assertEqual(mapped_streams(cmd), ["0:0", "0:1", "0:2", "0:4"])

    def test_nothing_is_dropped_by_default(self):
        cmd = []
        _task()._apply_video_container_track_mapping(cmd)
        self.assertEqual(mapped_streams(cmd), ["0:0", "0:1", "0:2", "0:3", "0:4"])


@unittest.skipUnless(ffmpeg_available(), "FFmpeg embarqué absent")
class LateCueEndToEndTests(unittest.TestCase):
    """Conversion réelle : le fichier doit dépasser ~71 min pour que le silence
    déborde, et la source doit être réencodée (en copie, rien ne casse)."""

    def test_a_lone_late_cue_no_longer_costs_the_audio(self):
        workdir = tempfile.mkdtemp()
        try:
            srt = os.path.join(workdir, "forces.srt")
            with open(srt, "w", encoding="utf-8") as handle:
                handle.write("1\n01:18:20,000 --> 01:18:22,000\nForce\n\n")

            source = os.path.join(workdir, "film.mkv")
            run_ffmpeg([
                "-f", "lavfi", "-i", "color=c=black:s=64x48:r=1:d=4775",
                "-f", "lavfi", "-i", "sine=d=4775",
                "-i", srt,
                "-map", "0:v", "-map", "1:a", "-map", "2:0",
                "-c:v", "libx264", "-preset", "ultrafast",
                "-c:a", "eac3", "-ac", "2", "-b:a", "96k",
                "-c:s", "copy", source,
            ])

            settings = normalize_format_settings("mp4", {})
            settings.update(video_mode="copy", audio_mode="convert", audio_bitrate="64k")
            output = os.path.join(workdir, "film.mp4")
            task = ConversionTask(FileProber().analyze(source), "mp4", settings,
                                  output_path=output)
            task.run()

            # L'invariant est le son complet. Le moyen dépend du FFmpeg embarqué :
            # jusqu'en 9.0.1 le muxeur perdait l'audio et AMC devait retirer le
            # sous-titre ; depuis 9.0.2 l'audio survit tout seul et la piste reste.
            streams = task._probe_stream_durations(output)
            audio = [value for kind, value, _is_cover in streams if kind == "audio"]
            self.assertGreater(min(audio), 4700)
            subtitles = [kind for kind, _value, _is_cover in streams if kind == "subtitle"]
            if task.dropped_subtitle_tracks:
                self.assertEqual(task.dropped_subtitle_tracks, {2})
                self.assertEqual(subtitles, [])
            else:
                self.assertEqual(subtitles, ["subtitle"])
        finally:
            shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
