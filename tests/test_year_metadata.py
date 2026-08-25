"""L'annee doit rester visible sous Windows apres conversion.

Signale sur AppleVis le 2026-08-21 : « the year is missing even though the box to
preserve full metadata and cover art is checked » — titre, artiste et album, eux,
s'affichaient.

Cause (verifiee en interrogeant le systeme de proprietes de l'Explorateur) : Windows
n'analyse la date d'un fichier que si elle vaut « AAAA » ou « AAAA-MM-JJ ». Les fichiers
iTunes / Apple Music portent un horodatage ISO complet (« 1998-05-03T07:00:00Z ») que
`-map_metadata 0` recopiait tel quel. ATTENTION en relisant ces tests : ffprobe relit
parfaitement l'horodatage brut, donc une assertion « le tag date existe » n'aurait rien
vu du bug. On verifie la VALEUR produite, et pour le MP3 la frame reellement ecrite.
"""

import os
import shutil
import tempfile
import unittest

from tests.helpers import ffmpeg_available, probe_tags, run_ffmpeg

from core.conversion import ConversionTask
from core.ffmpeg_helpers import normalize_date_tag
from core.merge import MergeTask
from core.metadata_retag import MetadataRetagTask
from core.probe import FileProber

SETTINGS = {
    "audio_mode": "convert", "rate_mode": "cbr", "audio_bitrate": "128k",
    "audio_sample_rate": "original", "audio_channels": "original",
    "ffmpeg_threads": "auto", "preserve_metadata": True, "flac_compression": "5",
}
ITUNES_DATE = "1998-05-03T07:00:00Z"


class NormalizeDateTagTests(unittest.TestCase):
    """None = « ne touche a rien » : soit la valeur passe deja sous Windows, soit on
    n'a pas trouve d'annee et il vaut mieux garder l'originale que d'en inventer une."""

    def test_values_windows_already_reads_are_left_alone(self):
        for value in ("1998", "1998-05-03"):
            with self.subTest(value=value):
                self.assertIsNone(normalize_date_tag(value))

    def test_unusable_values_are_left_alone(self):
        for value in ("", "   ", None, "unknown", 1998):
            with self.subTest(value=value):
                self.assertIsNone(normalize_date_tag(value))

    def test_flac_needs_a_bare_year(self):
        """Windows laisse la colonne Annee vide pour un FLAC dont le DATE vaut
        « 1998-05-03 », pourtant valide : la reduction n'est faite que la."""
        self.assertIsNone(normalize_date_tag("1998-05-03"))
        self.assertEqual("1998", normalize_date_tag("1998-05-03", year_only=True))
        self.assertIsNone(normalize_date_tag("1998", year_only=True))

    def test_unreadable_values_are_brought_back(self):
        cases = {
            ITUNES_DATE: "1998-05-03",   # iTunes / Apple Music
            "1998/05/03": "1998-05-03",
            "2001-1-4": "2001-01-04",    # mois et jour sur un chiffre
            "(1998)": "1998",
            "Released 1998": "1998",
        }
        for value, expected in cases.items():
            with self.subTest(value=value):
                self.assertEqual(expected, normalize_date_tag(value))


@unittest.skipUnless(ffmpeg_available(), "FFmpeg embarque absent de bin/")
class YearSurvivesConversionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.mkdtemp(prefix="amc-year-")
        cls.prober = FileProber()
        cls.itunes = cls.make_source("itunes.m4a", ITUNES_DATE)
        cls.plain = cls.make_source("simple.m4a", "1998")

    @classmethod
    def make_source(cls, name, date):
        path = os.path.join(cls.folder, name)
        run_ffmpeg([
            '-f', 'lavfi', '-i', 'sine=f=440:d=2', '-metadata', f'date={date}',
            '-metadata', 'title=Chanson', '-metadata', 'artist=Interprete', path,
        ])
        return path

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.folder, ignore_errors=True)

    def convert(self, source, name, target_format, meta=None):
        output = os.path.join(self.folder, name)
        task = ConversionTask(meta or self.prober.analyze(source), target_format,
                              dict(SETTINGS), output_path=output)
        task.run()
        return task, output

    def id3_version(self, path):
        with open(path, 'rb') as handle:
            header = handle.read(4)
        return header[3] if header[:3] == b'ID3' else None

    def test_itunes_timestamp_becomes_readable_in_mp3(self):
        task, output = self.convert(self.itunes, "itunes.mp3", "mp3")

        self.assertNotEqual(ITUNES_DATE, probe_tags(output).get('date'))
        self.assertTrue(probe_tags(output).get('date', '').startswith('1998'))
        self.assertEqual(3, self.id3_version(output))  # annee dans TYER, 4 chiffres

    def test_itunes_timestamp_becomes_readable_in_flac(self):
        """Le FLAC n'a pas de garde-fou ID3 : sans la normalisation il gardait
        l'horodatage brut. Et Windows y exige l'annee nue, d'ou « 1998 » et non
        « 1998-05-03 » comme pour les autres conteneurs."""
        task, output = self.convert(self.itunes, "itunes.flac", "flac")

        self.assertEqual("1998", probe_tags(output).get('date'))

    def test_a_plain_year_is_never_rewritten(self):
        task, output = self.convert(self.plain, "simple.mp3", "mp3")

        self.assertNotIn('-metadata', [
            token for index, token in enumerate(task.last_command)
            if token == '-metadata' and task.last_command[index + 1].startswith('date=')
        ])
        self.assertEqual("1998", probe_tags(output).get('date'))

    def test_a_date_edited_by_the_user_wins(self):
        meta = self.prober.analyze(self.itunes)
        meta.metadata_overrides = {"tags": {"date": "2003"}}

        task, output = self.convert(self.itunes, "edite.mp3", "mp3", meta=meta)

        self.assertEqual("2003", probe_tags(output).get('date'))

    def test_other_containers_never_receive_the_id3_option(self):
        """`-id3v2_version` est une option privee du muxeur mp3 : l'emettre ailleurs
        ferait echouer toute la commande."""
        for name, target in (("copie.flac", "flac"), ("copie.m4a", "aac")):
            with self.subTest(target=target):
                task, output = self.convert(self.plain, name, target)
                self.assertNotIn('-id3v2_version', task.last_command)
                self.assertTrue(os.path.isfile(output))

    def test_id3_option_is_placed_before_the_output_file(self):
        task, output = self.convert(self.plain, "place.mp3", "mp3")

        self.assertLess(task.last_command.index('-id3v2_version'),
                        task.last_command.index(output))

    def test_wma_gets_the_native_windows_attribute(self):
        """Windows ne lit pas le tag `date` generique dans un ASF : sans WM/Year
        l'annee d'un WMA reste invisible meme quand elle vaut deja « 1998 »."""
        task, output = self.convert(self.plain, "annee.wma", "wma")

        self.assertIn('WM/Year=1998', task.last_command)
        self.assertEqual("1998", probe_tags(output).get('wm/year'))

    def test_merge_writes_an_id3v2_3_header(self):
        """La fusion concat ne transporte pas les tags des sources : on verifie la
        version de l'en-tete, pas l'annee."""
        meta = self.prober.analyze(self.plain)
        output = os.path.join(self.folder, "fusion.mp3")
        MergeTask([meta, meta], "mp3", dict(SETTINGS), output).run()

        self.assertEqual(3, self.id3_version(output))

    def test_retag_in_place_keeps_the_year_visible(self):
        target = os.path.join(self.folder, "retag.mp3")
        run_ffmpeg(['-f', 'lavfi', '-i', 'sine=f=440:d=2', '-c:a', 'libmp3lame', target])
        meta = self.prober.analyze(target)

        MetadataRetagTask(meta, {"tags": {"date": "1998", "title": "Retague"}}).run()

        self.assertEqual(3, self.id3_version(target))
        self.assertEqual("1998", probe_tags(target).get('date'))


if __name__ == '__main__':
    unittest.main()
