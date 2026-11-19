"""Sonnerie iPhone (.m4r), demandée le 2026-11-19 : « le .m4r n'est pas supporté ».

Un .m4r est un fichier AAC dans un conteneur MP4, comme un .m4a. FFmpeg le lit
sans rien de particulier, mais ne sait pas quel conteneur écrire pour cette
extension : il faut lui imposer le muxer ipod, comme pour le M4B. L'iPhone
refuse une sonnerie de plus de 40 s : on garde 40 s à partir d'un début réglable.
"""

import os
import shutil
import subprocess
import tempfile
import unittest

from tests.helpers import ffmpeg_available, run_ffmpeg

from core.conversion import ConversionTask, get_output_extension
from core.ffmpeg_helpers import RINGTONE_MAX_SECONDS, get_ffprobe_path, ringtone_window
from core.formatting import (
    AUDIO_OUTPUT_FORMAT_KEYS,
    VIDEO_OUTPUT_FORMAT_KEYS,
    build_format_label,
    format_ringtone_start,
    normalize_format_settings,
    normalize_ringtone_start,
)
from core.merge import MergeTask
from core.probe import FileProber


def _m4r_settings(**overrides):
    settings = normalize_format_settings('m4r', overrides)
    settings['ffmpeg_threads'] = 'auto'
    return settings


class RingtoneWindowTests(unittest.TestCase):
    def test_keeps_forty_seconds_from_the_start(self):
        self.assertEqual(ringtone_window({}, 180.0), (0.0, 40.0))

    def test_chosen_start_is_honoured(self):
        self.assertEqual(ringtone_window({'ringtone_start': 72}, 180.0), (72.0, 40.0))

    def test_short_source_is_kept_whole(self):
        self.assertEqual(ringtone_window({}, 20.0), (0.0, 20.0))

    def test_end_of_file_shortens_the_ringtone(self):
        self.assertEqual(ringtone_window({'ringtone_start': 170}, 180.0), (170.0, 10.0))

    def test_start_past_the_end_keeps_the_last_forty_seconds(self):
        """Plutôt qu'un fichier vide : un début trop loin ramène à la fin."""
        self.assertEqual(ringtone_window({'ringtone_start': 500}, 180.0), (140.0, 40.0))

    def test_unknown_duration_asks_for_forty_seconds(self):
        self.assertEqual(ringtone_window({'ringtone_start': 5}, None), (5.0, 40.0))

    def test_garbage_start_falls_back_to_zero(self):
        self.assertEqual(ringtone_window({'ringtone_start': 'abc'}, 60.0), (0.0, 40.0))


class RingtoneFormatTests(unittest.TestCase):
    def test_m4r_is_an_audio_and_extraction_output(self):
        self.assertIn('m4r', AUDIO_OUTPUT_FORMAT_KEYS)
        self.assertIn('m4r', VIDEO_OUTPUT_FORMAT_KEYS)

    def test_extension_is_m4r(self):
        self.assertEqual(get_output_extension('m4r'), 'm4r')

    def test_labels(self):
        self.assertEqual(build_format_label('m4r'), 'M4R - iPhone Ringtone')
        self.assertEqual(build_format_label('m4r', 'video'), 'M4R - iPhone Ringtone (Extract)')

    def test_start_is_normalized_and_shown_in_the_summary(self):
        settings = normalize_format_settings('m4r', {'ringtone_start': '72.9'})
        self.assertEqual(settings['ringtone_start'], 72)
        self.assertIn('40 s from 1:12', settings['summary'])

    def test_start_bounds(self):
        self.assertEqual(normalize_ringtone_start(-5), 0)
        self.assertEqual(normalize_ringtone_start(10 ** 9), 86399)
        self.assertEqual(normalize_ringtone_start(None), 0)
        self.assertEqual(format_ringtone_start(3725), '1:02:05')

    def test_other_formats_carry_no_ringtone_setting(self):
        self.assertNotIn('ringtone_start', normalize_format_settings('m4b', {}))


class RingtoneCommandTests(unittest.TestCase):
    """La commande, sans lancer FFmpeg (Popen intercepté)."""

    def _command(self, settings, duration=180.0):
        captured = {}

        class _Stop(Exception):
            pass

        def fake_popen(cmd, **kwargs):
            captured['cmd'] = cmd
            raise _Stop()

        tmp = tempfile.mkdtemp(prefix='amc_m4r_cmd_')
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        source = os.path.join(tmp, 'song.mp3')
        open(source, 'wb').close()

        class _Meta:
            full_path = source
            video_tracks = []
            audio_tracks = []
            subtitle_tracks = []
            has_video = False

        meta = _Meta()
        meta.duration = duration
        task = ConversionTask(meta, 'm4r', settings, output_path=os.path.join(tmp, 'song.m4r'))
        original = subprocess.Popen
        subprocess.Popen = fake_popen
        try:
            with self.assertRaises(_Stop):
                task.run()
        finally:
            subprocess.Popen = original
        return task, captured['cmd']

    def test_ipod_muxer_aac_and_window(self):
        task, cmd = self._command(_m4r_settings(ringtone_start=72))
        self.assertEqual(cmd[cmd.index('-f') + 1], 'ipod')
        self.assertEqual(cmd[cmd.index('-c:a') + 1], 'aac')
        self.assertEqual(cmd[cmd.index('-ss') + 1], '00:01:12.000')
        self.assertLess(cmd.index('-ss'), cmd.index('-i'))
        self.assertEqual(cmd[cmd.index('-t') + 1], '00:00:40.000')
        self.assertGreater(cmd.index('-t'), cmd.index('-i'))
        self.assertEqual(task.duration, 40.0)

    def test_no_seek_from_the_beginning(self):
        _, cmd = self._command(_m4r_settings())
        self.assertNotIn('-ss', cmd)
        self.assertIn('-t', cmd)


@unittest.skipUnless(ffmpeg_available(), "FFmpeg embarqué absent (bin/ffmpeg.exe)")
class RingtoneEndToEndTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix='amc_m4r_')
        cls.song = os.path.join(cls.tmp, 'song.mp3')
        run_ffmpeg(['-f', 'lavfi', '-i', 'sine=frequency=440:duration=90',
                    '-c:a', 'libmp3lame', '-b:a', '128k', cls.song])
        cls.short = os.path.join(cls.tmp, 'short.m4a')
        run_ffmpeg(['-f', 'lavfi', '-i', 'sine=frequency=660:duration=12',
                    '-c:a', 'aac', '-b:a', '128k', cls.short])
        cls.clip = os.path.join(cls.tmp, 'clip.mp4')
        run_ffmpeg(['-f', 'lavfi', '-i', 'testsrc=size=160x120:rate=10:duration=70',
                    '-f', 'lavfi', '-i', 'sine=frequency=330:duration=70',
                    '-c:v', 'libx264', '-preset', 'ultrafast', '-c:a', 'aac', '-shortest', cls.clip])

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _probe(self, path):
        out = subprocess.run(
            [get_ffprobe_path(), '-v', 'error', '-show_entries',
             'format=format_name,duration:stream=codec_type,codec_name',
             '-of', 'default=noprint_wrappers=1', path],
            capture_output=True, text=True, timeout=60,
        ).stdout
        info = {'streams': []}
        for line in out.splitlines():
            key, _sep, value = line.partition('=')
            if key == 'codec_type':
                info['streams'].append(value)
            else:
                info[key] = value
        return info

    def _convert(self, source, name, **settings):
        meta = FileProber().analyze(source)
        output = os.path.join(self.tmp, name)
        ConversionTask(meta, 'm4r', _m4r_settings(**settings), output_path=output).run()
        return self._probe(output)

    def test_song_becomes_a_forty_second_ringtone(self):
        info = self._convert(self.song, 'song.m4r', ringtone_start=30)
        self.assertEqual(info['codec_name'], 'aac')
        self.assertIn('mp4', info['format_name'])
        self.assertAlmostEqual(float(info['duration']), RINGTONE_MAX_SECONDS, delta=0.5)

    def test_end_of_song_is_not_reported_as_truncated(self):
        """90 s, début à 70 s : 20 s de sonnerie, et pas de faux « trop court »."""
        info = self._convert(self.song, 'tail.m4r', ringtone_start=70)
        self.assertAlmostEqual(float(info['duration']), 20.0, delta=0.5)

    def test_short_file_is_kept_whole(self):
        info = self._convert(self.short, 'short.m4r')
        self.assertAlmostEqual(float(info['duration']), 12.0, delta=0.5)

    def test_copy_mode_from_m4a_keeps_the_window(self):
        info = self._convert(self.short, 'short_copy.m4r', audio_mode='copy', ringtone_start=2)
        self.assertAlmostEqual(float(info['duration']), 10.0, delta=0.5)

    def test_video_soundtrack_becomes_a_ringtone_without_picture(self):
        info = self._convert(self.clip, 'clip.m4r', ringtone_start=10)
        self.assertEqual(info['streams'], ['audio'])
        self.assertAlmostEqual(float(info['duration']), RINGTONE_MAX_SECONDS, delta=0.5)

    def test_m4r_is_read_as_audio_input(self):
        ringtone = os.path.join(self.tmp, 'input.m4r')
        run_ffmpeg(['-f', 'lavfi', '-i', 'sine=frequency=550:duration=8',
                    '-c:a', 'aac', '-f', 'ipod', ringtone])
        meta = FileProber().analyze(ringtone)
        self.assertEqual(len(meta.audio_tracks), 1)
        self.assertFalse(meta.video_tracks)
        output = os.path.join(self.tmp, 'from_ringtone.mp3')
        ConversionTask(meta, 'mp3', normalize_format_settings('mp3', {}), output_path=output).run()
        self.assertAlmostEqual(float(self._probe(output)['duration']), 8.0, delta=0.5)

    def test_merge_into_a_ringtone(self):
        # Le concat de FFmpeg exige un même codec partout : deux MP3.
        metas = [FileProber().analyze(self.song), FileProber().analyze(self.song)]
        output = os.path.join(self.tmp, 'merged.m4r')
        MergeTask(metas, 'm4r', _m4r_settings(ringtone_start=100), output).run()
        info = self._probe(output)
        self.assertEqual(info['codec_name'], 'aac')
        self.assertAlmostEqual(float(info['duration']), RINGTONE_MAX_SECONDS, delta=0.5)


if __name__ == '__main__':
    unittest.main()
