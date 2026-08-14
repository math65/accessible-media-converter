"""Réglages de pistes — non-régression du mapping par lot.

Bug terrain (2026-08-14, v1.20.0) : « Gérer les pistes (N fichiers)… » recopiait la
configuration telle quelle ; les entrées visant un flux absent du fichier cible
étaient conservées et produisaient un `-map 0:4` dans le vide, ce qui faisait
échouer TOUTE la conversion de ce fichier.
"""

import unittest

from tests.helpers import audio_track, make_media, subtitle_track, video_track

from core.track_settings import (
    build_default_track_settings,
    get_kept_track_entries,
    normalize_track_settings,
)


def kept_indices(track_settings, track_type):
    return [entry["original_index"] for entry in get_kept_track_entries(track_settings, track_type)]


class BatchTrackConfigTests(unittest.TestCase):
    def setUp(self):
        # Référence : 1 vidéo, 3 audio, 1 sous-titre (flux 0 à 4).
        self.reference = make_media(
            video=[video_track(0)],
            audio=[audio_track(1), audio_track(2), audio_track(3)],
            subtitle=[subtitle_track(4)],
        )
        self.reference_config = build_default_track_settings(self.reference)

    def test_entries_missing_from_target_are_dropped(self):
        target = make_media(video=[video_track(0)], audio=[audio_track(1), audio_track(2)])
        target.track_settings = self.reference_config

        normalized = normalize_track_settings(target.track_settings, target)

        self.assertEqual(kept_indices(normalized, "audio"), [1, 2])
        self.assertEqual(kept_indices(normalized, "subtitle"), [])
        self.assertEqual(kept_indices(normalized, "video"), [0])

    def test_matching_entries_keep_their_choices(self):
        """Le lot doit continuer à propager les choix réels de l'utilisateur."""
        config = build_default_track_settings(self.reference)
        config["audio_tracks"][1]["keep"] = False  # l'utilisateur retire la 2e piste audio

        target = make_media(
            video=[video_track(0)], audio=[audio_track(1), audio_track(2), audio_track(3)]
        )
        target.track_settings = config

        normalized = normalize_track_settings(target.track_settings, target)

        self.assertEqual(kept_indices(normalized, "audio"), [1, 3])

    def test_legacy_entries_also_drop_unknown_streams(self):
        """Entrées d'anciennes versions (sans bloc `dispositions`)."""
        target = make_media(video=[video_track(0)], audio=[audio_track(1)])
        legacy = {
            "video_tracks": [{"original_index": 0, "keep": True, "default": True}],
            "audio_tracks": [
                {"original_index": 1, "keep": True, "default": True},
                {"original_index": 9, "keep": True, "default": False},  # n'existe pas
            ],
            "subtitle_tracks": [],
        }
        target.track_settings = legacy

        normalized = normalize_track_settings(target.track_settings, target)

        self.assertEqual(kept_indices(normalized, "audio"), [1])

    def test_unknown_entries_survive_when_source_streams_are_unknown(self):
        """Sans meta, on ne peut rien vérifier : ne rien jeter (sérialisation)."""
        normalized = normalize_track_settings(self.reference_config, None)

        self.assertEqual(kept_indices(normalized, "audio"), [1, 2, 3])


class UnusableTrackTests(unittest.TestCase):
    """Capture TV abîmée : flux audio sans débit d'échantillonnage."""

    def test_unreadable_audio_is_not_kept_by_default(self):
        meta = make_media(
            video=[video_track(4)],
            audio=[audio_track(5), audio_track(8, sample_rate=None)],
        )

        defaults = build_default_track_settings(meta)

        self.assertEqual(kept_indices(defaults, "audio"), [5])
        entries = {entry["original_index"]: entry for entry in defaults["audio_tracks"]}
        self.assertTrue(entries[5]["usable"])
        self.assertFalse(entries[8]["usable"])

    def test_readable_audio_stays_usable(self):
        meta = make_media(video=[video_track(0)], audio=[audio_track(1)])

        defaults = build_default_track_settings(meta)

        self.assertEqual(kept_indices(defaults, "audio"), [1])
        self.assertTrue(defaults["audio_tracks"][0]["usable"])


if __name__ == "__main__":
    unittest.main()
