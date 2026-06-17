"""Encoding presets — save / apply / import / export reusable conversion profiles.

A preset bundles, under a name, everything the user would otherwise re-enter by
hand: the output **format**, its **encoding settings**, the **output preferences**
(mode + custom folder + preserve-subfolder-structure) and an optional **metadata
template** (shared tags). It is *not* a separate conversion path — applying a preset
simply pours these values back into the existing ``settings_store`` (see
``ui/main_window.on_open_presets``).

Pure logic, no gettext: every user-facing string lives in the UI layer
(``ui/presets_dialog.py``). Presets persist to ``presets.json`` in the config dir,
separate from ``config.json`` so the file body is exactly the import/export payload.
"""

import json
import os

from core.debug_session import ensure_config_dir, get_config_dir
from core.formatting import (
    AUDIO_OUTPUT_FORMAT_KEYS,
    IMAGE_OUTPUT_FORMAT_KEYS,
    VALID_OUTPUT_MODES,
    VIDEO_OUTPUT_FORMAT_KEYS,
    normalize_format_settings,
)
from core.metadata_edit import METADATA_TAG_KEYS

PRESETS_FILENAME = "presets.json"
PRESETS_FILE_VERSION = 1
EXPORT_KIND = "presets"
EXPORT_APP = "amc"

VALID_CATEGORIES = ("audio", "video", "image")

_FORMAT_KEYS_BY_CATEGORY = {
    "audio": AUDIO_OUTPUT_FORMAT_KEYS,
    "video": VIDEO_OUTPUT_FORMAT_KEYS,
    "image": IMAGE_OUTPUT_FORMAT_KEYS,
}


def get_presets_path():
    return os.path.join(get_config_dir(), PRESETS_FILENAME)


def _normalize_output(raw):
    """Validate the optional output-preferences block; return {} if absent/empty."""
    if not isinstance(raw, dict):
        return {}
    output = {}
    mode = raw.get("output_mode")
    if mode in VALID_OUTPUT_MODES:
        output["output_mode"] = mode
    if "custom_output_path" in raw:
        output["custom_output_path"] = str(raw.get("custom_output_path") or "")
    if "preserve_folder_structure" in raw:
        output["preserve_folder_structure"] = bool(raw.get("preserve_folder_structure"))
    return output


def _normalize_metadata(raw):
    """Keep only known tag keys with non-empty string values, in field order."""
    if not isinstance(raw, dict):
        return {}
    tags = {}
    for key in METADATA_TAG_KEYS:
        if key in raw and raw[key] is not None:
            value = str(raw[key])
            if value:
                tags[key] = value
    return tags


def normalize_preset(raw):
    """Return a validated preset dict, or ``None`` if it can't be salvaged.

    A preset is rejected only when its identity is unusable (no name, unknown
    category, or a format that isn't valid for that category). Sub-blocks
    (output / metadata) degrade to empty rather than failing the whole preset.
    """
    if not isinstance(raw, dict):
        return None

    name = str(raw.get("name") or "").strip()
    if not name:
        return None

    category = raw.get("category")
    if category not in VALID_CATEGORIES:
        return None

    format_key = raw.get("format")
    if format_key not in _FORMAT_KEYS_BY_CATEGORY[category]:
        return None

    return {
        "name": name,
        "category": category,
        "format": format_key,
        "settings": normalize_format_settings(format_key, raw.get("settings")),
        "output": _normalize_output(raw.get("output")),
        "metadata": _normalize_metadata(raw.get("metadata")),
    }


def _normalize_preset_list(raw_presets):
    presets = []
    if isinstance(raw_presets, list):
        for entry in raw_presets:
            preset = normalize_preset(entry)
            if preset is not None:
                presets.append(preset)
    return presets


def load_presets():
    """Read and normalize the presets file. Never raises: corrupt/missing → []."""
    path = get_presets_path()
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception:
        return []
    if not isinstance(data, dict):
        return []
    return _normalize_preset_list(data.get("presets"))


def save_presets(presets):
    ensure_config_dir()
    payload = {"version": PRESETS_FILE_VERSION, "presets": list(presets)}
    with open(get_presets_path(), "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=4, ensure_ascii=False)


def find_preset(presets, name):
    """Return the preset matching ``name`` (case-insensitive), or ``None``."""
    target = str(name or "").strip().lower()
    for preset in presets:
        if preset.get("name", "").lower() == target:
            return preset
    return None


def upsert_preset(presets, preset):
    """Add ``preset`` or replace an existing one with the same name (case-insensitive).

    Returns a new list (input is not mutated). The replacement keeps the new
    preset's position-by-name: an existing match is overwritten in place,
    otherwise the preset is appended.
    """
    name = preset.get("name", "").lower()
    result = []
    replaced = False
    for existing in presets:
        if existing.get("name", "").lower() == name:
            result.append(preset)
            replaced = True
        else:
            result.append(existing)
    if not replaced:
        result.append(preset)
    return result


def delete_preset(presets, name):
    target = str(name or "").strip().lower()
    return [p for p in presets if p.get("name", "").lower() != target]


def strip_export_fields(presets, include_output=True, include_metadata=True):
    """Return copies of ``presets`` with optional blocks cleared for export.

    The format and encoding settings are a preset's essence and always kept.
    The output destination and the metadata template are portability-sensitive
    (a custom folder rarely makes sense on another machine), so the export UI
    lets the user drop them. Cleared blocks become ``{}`` rather than being
    removed, so a re-import still normalizes cleanly.
    """
    result = []
    for preset in presets:
        copy = dict(preset)
        if not include_output:
            copy["output"] = {}
        if not include_metadata:
            copy["metadata"] = {}
        result.append(copy)
    return result


def export_presets(path, presets):
    """Write a portable bundle of the given presets to ``path``."""
    payload = {
        "app": EXPORT_APP,
        "kind": EXPORT_KIND,
        "version": PRESETS_FILE_VERSION,
        "presets": list(presets),
    }
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=4, ensure_ascii=False)


class PresetImportError(Exception):
    """Raised when an import file can't be read or isn't a presets bundle."""


def import_presets(path):
    """Load and normalize presets from an exported (or raw) presets file.

    Returns the list of valid presets (invalid entries are silently skipped).
    Raises ``PresetImportError`` only when the file is unreadable, not JSON, or
    not a presets bundle at all.
    """
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError) as exc:
        raise PresetImportError(str(exc)) from exc

    if not isinstance(data, dict) or "presets" not in data:
        raise PresetImportError("Not a presets file.")
    kind = data.get("kind")
    if kind is not None and kind != EXPORT_KIND:
        raise PresetImportError("Not a presets file.")

    return _normalize_preset_list(data.get("presets"))
