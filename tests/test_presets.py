"""Presets — visibilité d'un preset selon l'onglet.

Bug terrain (2026-08-18, v1.20.1, Sèb) : avec une vidéo chargée et la sortie
« MP3 - Audio (extraction) » sélectionnée, les presets audio n'apparaissaient
pas. La liste filtrait sur la catégorie enregistrée (l'onglet d'origine) alors
que l'onglet vidéo produit AUSSI tous les formats audio.
"""

import unittest

from tests.helpers import REPO_ROOT  # noqa: F401  (ajoute la racine au sys.path)

from core.presets import is_preset_applicable, normalize_preset


def preset(category, format_key, name="P"):
    built = normalize_preset({"name": name, "category": category, "format": format_key})
    assert built is not None, (category, format_key)
    return built


class PresetVisibilityTests(unittest.TestCase):
    def test_audio_preset_visible_on_video_tab(self):
        """Le cas du rapport : preset MP3 créé côté audio, onglet vidéo actif."""
        self.assertTrue(is_preset_applicable(preset("audio", "mp3"), "video"))

    def test_video_tab_audio_preset_visible_on_audio_tab(self):
        """Réciproque : preset MP3 enregistré depuis l'onglet vidéo."""
        self.assertTrue(is_preset_applicable(preset("video", "mp3"), "audio"))

    def test_container_video_preset_hidden_on_audio_tab(self):
        """Un preset MP4 n'a rien à faire dans l'onglet audio."""
        self.assertFalse(is_preset_applicable(preset("video", "mp4"), "audio"))

    def test_image_presets_isolated(self):
        image_preset = preset("image", "jpeg")
        self.assertTrue(is_preset_applicable(image_preset, "image"))
        self.assertFalse(is_preset_applicable(image_preset, "audio"))
        self.assertFalse(is_preset_applicable(image_preset, "video"))
        self.assertFalse(is_preset_applicable(preset("audio", "flac"), "image"))

    def test_unknown_category_is_never_applicable(self):
        self.assertFalse(is_preset_applicable(preset("audio", "mp3"), "unknown"))

    def test_every_audio_format_reaches_the_video_tab(self):
        from core.formatting import AUDIO_OUTPUT_FORMAT_KEYS
        for key in AUDIO_OUTPUT_FORMAT_KEYS:
            with self.subTest(format=key):
                self.assertTrue(is_preset_applicable(preset("audio", key), "video"))


if __name__ == "__main__":
    unittest.main()
