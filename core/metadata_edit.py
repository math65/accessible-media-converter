"""Pure logic for editing file-level metadata (tags + cover art).

Shared by the conversion path (``core/conversion.py``) and the in-place
re-tag path (``core/metadata_retag.py``). No gettext at module level: the
labels are msgids consumed by the UI, which calls ``_()`` itself.
"""


# (ffmpeg metadata key, UI label msgid) in display / command order.
METADATA_TAG_FIELDS = (
    ("title", "Title"),
    ("artist", "Artist"),
    ("album", "Album"),
    ("album_artist", "Album artist"),
    ("composer", "Composer"),
    ("date", "Year"),
    ("track", "Track number"),
    ("disc", "Disc number"),
    ("genre", "Genre"),
    ("comment", "Comment"),
)

METADATA_TAG_KEYS = tuple(key for key, _label in METADATA_TAG_FIELDS)

# ffprobe tag aliases -> our canonical field key (keys are lowercased on read).
_TAG_ALIASES = {
    "title": "title",
    "artist": "artist",
    "album": "album",
    "album_artist": "album_artist",
    "albumartist": "album_artist",
    "album artist": "album_artist",
    "composer": "composer",
    "date": "date",
    "year": "date",
    "track": "track",
    "tracknumber": "track",
    "disc": "disc",
    "discnumber": "disc",
    "genre": "genre",
    "comment": "comment",
}

# Output audio formats whose container can embed a cover (attached_pic) image.
# Cover embedding during *conversion* is limited to audio targets: mixing a new
# cover with a re-encoded video stream in a container is intentionally deferred.
COVER_CAPABLE_AUDIO = ("mp3", "aac", "alac", "flac")
COVER_CAPABLE_FORMATS = COVER_CAPABLE_AUDIO

COVER_STREAM_TITLE = "Album cover"

VALID_COVER_ACTIONS = ("keep", "replace", "remove")


def format_supports_cover(format_key):
    return str(format_key or "").lower() in COVER_CAPABLE_FORMATS


def source_supports_cover(format_name):
    """True if a source container (ffprobe format_name) can embed a cover.

    Used by the in-place re-tag path where the target is the source format.
    """
    name = str(format_name or "").lower()
    if not name:
        return False
    tokens = {token.strip() for token in name.split(",")}
    cover_tokens = {"mp3", "mov", "mp4", "m4a", "ipod", "flac", "matroska", "matroska,webm"}
    return bool(tokens & cover_tokens) or "mp4" in name or "matroska" in name


def read_prefill_tags(format_tags):
    """Map ffprobe format tags to our editor field keys (single-file prefill)."""
    prefilled = {key: "" for key in METADATA_TAG_KEYS}
    if not isinstance(format_tags, dict):
        return prefilled

    for raw_key, value in format_tags.items():
        canonical = _TAG_ALIASES.get(str(raw_key).lower())
        if canonical and not prefilled.get(canonical):
            prefilled[canonical] = "" if value is None else str(value)
    return prefilled


def normalize_metadata_overrides(overrides):
    """Return {} when nothing to apply, else a clean
    {"tags": {key: value, ...}, "cover": {"action": ..., "path": ...}} dict.

    ``tags`` keeps only known keys, in field order. ``cover`` defaults to keep.
    """
    if not isinstance(overrides, dict):
        return {}

    raw_tags = overrides.get("tags", {})
    tags = {}
    if isinstance(raw_tags, dict):
        for key in METADATA_TAG_KEYS:
            if key in raw_tags and raw_tags[key] is not None:
                tags[key] = str(raw_tags[key])

    raw_cover = overrides.get("cover", {})
    action = "keep"
    path = ""
    if isinstance(raw_cover, dict):
        candidate = str(raw_cover.get("action", "keep") or "keep").lower()
        if candidate in VALID_COVER_ACTIONS:
            action = candidate
        path = str(raw_cover.get("path", "") or "")

    if action == "replace" and not path:
        action = "keep"

    cover = {"action": action}
    if action == "replace":
        cover["path"] = path

    normalized = {"tags": tags, "cover": cover}
    if not overrides_are_effective(normalized):
        return {}
    return normalized


def overrides_are_effective(overrides):
    if not isinstance(overrides, dict):
        return False
    if overrides.get("tags"):
        return True
    cover = overrides.get("cover", {})
    return isinstance(cover, dict) and cover.get("action", "keep") != "keep"


def has_metadata_overrides(meta):
    return overrides_are_effective(getattr(meta, "metadata_overrides", None))


def get_metadata_overrides(meta):
    return normalize_metadata_overrides(getattr(meta, "metadata_overrides", None))


def build_tag_metadata_args(tags):
    """Build ['-metadata', 'key=value', ...] in field order. Empty value clears."""
    args = []
    if not isinstance(tags, dict):
        return args
    for key in METADATA_TAG_KEYS:
        if key in tags:
            args.extend(["-metadata", f"{key}={tags[key]}"])
    return args


def cover_stream_args(output_video_index=0):
    """Disposition + title for the cover stream at output video index N.

    Caller is responsible for ``-i <cover>``, the ``-map`` directives and
    ``-c:v copy`` (the surrounding command differs between audio and video).
    """
    spec = f"v:{output_video_index}"
    return [
        f"-disposition:{spec}",
        "attached_pic",
        f"-metadata:s:{spec}",
        f"title={COVER_STREAM_TITLE}",
    ]
