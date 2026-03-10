import builtins


AUDIO_OUTPUT_FORMAT_KEYS = ("mp3", "aac", "wav", "flac", "alac", "ogg", "wma")
VIDEO_OUTPUT_FORMAT_KEYS = ("mp4", "mkv", *AUDIO_OUTPUT_FORMAT_KEYS)
VIDEO_CONTAINER_FORMAT_KEYS = ("mp4", "mkv")
LOSSLESS_AUDIO_FORMAT_KEYS = ("wav", "flac", "alac")
VALID_OUTPUT_MODES = ("source", "custom", "ask")
VALID_EXISTING_OUTPUT_POLICIES = ("rename", "overwrite", "skip")
MIN_CONCURRENT_JOBS = 1
MAX_CONCURRENT_JOBS = 4
DEFAULT_CONCURRENT_JOBS = 2


DEFAULT_FORMAT_SETTINGS = {
    "mp3": {
        "audio_mode": "convert",
        "audio_normalize_streaming": False,
        "rate_mode": "cbr",
        "audio_bitrate": "192k",
        "audio_qscale": 0,
        "audio_sample_rate": "original",
        "audio_channels": "2",
    },
    "aac": {
        "audio_mode": "convert",
        "audio_normalize_streaming": False,
        "rate_mode": "cbr",
        "audio_bitrate": "192k",
        "audio_qscale": 3,
        "audio_sample_rate": "original",
        "audio_channels": "2",
    },
    "ogg": {
        "audio_mode": "convert",
        "audio_normalize_streaming": False,
        "audio_qscale": 6,
        "audio_sample_rate": "original",
        "audio_channels": "2",
    },
    "wma": {
        "audio_mode": "convert",
        "audio_normalize_streaming": False,
        "audio_bitrate": "128k",
        "audio_sample_rate": "original",
        "audio_channels": "2",
    },
    "wav": {
        "audio_mode": "convert",
        "audio_normalize_streaming": False,
        "audio_sample_rate": "original",
        "audio_bit_depth": "original",
        "audio_channels": "original",
    },
    "flac": {
        "audio_mode": "convert",
        "audio_normalize_streaming": False,
        "audio_sample_rate": "original",
        "audio_bit_depth": "original",
        "flac_compression": 5,
        "audio_channels": "original",
    },
    "alac": {
        "audio_mode": "convert",
        "audio_normalize_streaming": False,
        "audio_sample_rate": "original",
        "audio_bit_depth": "original",
        "audio_channels": "original",
    },
    "mp4": {
        "video_mode": "convert",
        "video_crf": 23,
        "audio_mode": "convert",
        "audio_normalize_streaming": False,
        "rate_mode": "cbr",
        "audio_bitrate": "192k",
        "audio_qscale": 3,
        "audio_sample_rate": "original",
        "audio_channels": "2",
    },
    "mkv": {
        "video_mode": "convert",
        "video_crf": 23,
        "audio_mode": "convert",
        "audio_normalize_streaming": False,
        "rate_mode": "cbr",
        "audio_bitrate": "192k",
        "audio_qscale": 3,
        "audio_sample_rate": "original",
        "audio_channels": "2",
    },
}

APP_DEFAULT_SETTINGS = {
    "last_format_audio": "mp3",
    "last_format_video": "mp4",
    "output_mode": "source",
    "custom_output_path": "",
    "existing_output_policy": "rename",
    "open_output_folder_after_batch": False,
    "max_concurrent_jobs": DEFAULT_CONCURRENT_JOBS,
    "continue_on_error": True,
    "debug_enabled": False,
    "debug_restore_pending": False,
}


def _translate(msgid):
    translator = builtins.__dict__.get("_")
    if callable(translator):
        return translator(msgid)
    return msgid


def _translatef(msgid, **kwargs):
    return _translate(msgid).format(**kwargs)


def build_format_label(format_key, context="audio"):
    if context == "video" and format_key in AUDIO_OUTPUT_FORMAT_KEYS:
        extraction_labels = {
            "mp3": _translate("MP3 - Audio (Extract)"),
            "aac": _translate("AAC - Audio (Extract)"),
            "wav": _translate("WAV - Audio (Extract)"),
            "flac": _translate("FLAC - Audio (Extract)"),
            "alac": _translate("ALAC - Audio (Extract)"),
            "ogg": _translate("OGG - Audio (Extract)"),
            "wma": _translate("WMA - Audio (Extract)"),
        }
        return extraction_labels.get(format_key, format_key.upper())

    labels = {
        "mp3": _translate("MP3 - Audio"),
        "aac": _translate("AAC - Audio (M4A)"),
        "wav": _translate("WAV - Audio (Lossless)"),
        "flac": _translate("FLAC - Audio (Lossless)"),
        "alac": _translate("ALAC - Audio (Apple Lossless)"),
        "ogg": _translate("OGG - Audio (Vorbis)"),
        "wma": _translate("WMA - Audio (Legacy)"),
        "mp4": _translate("MP4 - Video (H.264)"),
        "mkv": _translate("MKV - Video"),
    }
    return labels.get(format_key, format_key.upper())


def build_default_settings_store():
    store = {}
    for format_key, settings in DEFAULT_FORMAT_SETTINGS.items():
        store[format_key] = normalize_format_settings(format_key, settings)
    store.update(APP_DEFAULT_SETTINGS)
    return store


def normalize_format_settings(format_key, settings):
    normalized = dict(DEFAULT_FORMAT_SETTINGS[format_key])
    if isinstance(settings, dict):
        normalized.update(settings)
    normalized["audio_normalize_streaming"] = bool(normalized.get("audio_normalize_streaming", False))
    normalized["summary"] = build_format_summary(format_key, normalized)
    return normalized


def normalize_settings_store(settings_store):
    normalized = build_default_settings_store()
    if not isinstance(settings_store, dict):
        return normalized

    for key, value in settings_store.items():
        if key in DEFAULT_FORMAT_SETTINGS and isinstance(value, dict):
            normalized[key] = normalize_format_settings(key, value)
        elif key not in DEFAULT_FORMAT_SETTINGS:
            normalized[key] = value

    if normalized.get("last_format_audio") not in AUDIO_OUTPUT_FORMAT_KEYS:
        normalized["last_format_audio"] = APP_DEFAULT_SETTINGS["last_format_audio"]
    if normalized.get("last_format_video") not in VIDEO_OUTPUT_FORMAT_KEYS:
        normalized["last_format_video"] = APP_DEFAULT_SETTINGS["last_format_video"]
    if normalized.get("output_mode") not in VALID_OUTPUT_MODES:
        normalized["output_mode"] = APP_DEFAULT_SETTINGS["output_mode"]
    if normalized.get("existing_output_policy") not in VALID_EXISTING_OUTPUT_POLICIES:
        normalized["existing_output_policy"] = APP_DEFAULT_SETTINGS["existing_output_policy"]

    normalized["open_output_folder_after_batch"] = bool(
        normalized.get("open_output_folder_after_batch", APP_DEFAULT_SETTINGS["open_output_folder_after_batch"])
    )
    normalized["continue_on_error"] = bool(
        normalized.get("continue_on_error", APP_DEFAULT_SETTINGS["continue_on_error"])
    )
    normalized["max_concurrent_jobs"] = _normalize_concurrent_jobs(
        normalized.get("max_concurrent_jobs", APP_DEFAULT_SETTINGS["max_concurrent_jobs"])
    )

    return normalized


def _normalize_concurrent_jobs(value):
    try:
        jobs = int(value)
    except (TypeError, ValueError):
        jobs = DEFAULT_CONCURRENT_JOBS
    return min(max(jobs, MIN_CONCURRENT_JOBS), MAX_CONCURRENT_JOBS)


def build_format_summary(format_key, settings):
    if format_key in VIDEO_CONTAINER_FORMAT_KEYS:
        return _build_video_summary(settings)
    return _build_audio_summary(format_key, settings, include_channels=True)


def _build_video_summary(settings):
    if settings.get("video_mode", "convert") == "copy":
        video_summary = _translate("Video: Copy")
    else:
        video_summary = _translatef(
            "H.264 CRF {crf}",
            crf=settings.get("video_crf", DEFAULT_FORMAT_SETTINGS["mp4"]["video_crf"]),
        )

    if settings.get("audio_mode", "convert") == "copy":
        audio_summary = _translate("Audio: Copy")
    else:
        audio_parts = [_build_audio_mode_summary("mp4", settings)]
        if _should_include_audio_normalization(settings):
            audio_parts.append(_translate("Normalized -16 LUFS"))
        audio_summary = _translatef("Audio: {summary}", summary=" / ".join(audio_parts))

    return " / ".join([video_summary, audio_summary])


def _build_audio_summary(format_key, settings, include_channels):
    parts = [_build_audio_mode_summary(format_key, settings)]
    if include_channels and _should_include_audio_channels(format_key, settings):
        parts.append(_build_channel_summary(settings.get("audio_channels", "original")))
    if _should_include_audio_normalization(settings):
        parts.append(_translate("Normalized -16 LUFS"))
    return " / ".join(parts)


def _build_audio_mode_summary(format_key, settings):
    if settings.get("audio_mode", "convert") == "copy":
        return _translate("Copy")

    if format_key in LOSSLESS_AUDIO_FORMAT_KEYS:
        return _translate("Lossless")

    if settings.get("rate_mode", "cbr") == "vbr":
        quality = settings.get(
            "audio_qscale",
            DEFAULT_FORMAT_SETTINGS.get(format_key, DEFAULT_FORMAT_SETTINGS["mp3"]).get(
                "audio_qscale", 0
            ),
        )
        return _translatef("VBR Q{quality}", quality=quality)

    bitrate = settings.get(
        "audio_bitrate",
        DEFAULT_FORMAT_SETTINGS.get(format_key, DEFAULT_FORMAT_SETTINGS["mp3"]).get(
            "audio_bitrate", "192k"
        ),
    )
    return _translatef("CBR {bitrate}", bitrate=bitrate)


def _build_channel_summary(channels):
    channels_key = str(channels)
    if channels_key == "2":
        return _translate("Stereo")
    if channels_key == "1":
        return _translate("Mono")
    return _translate("Original Channels")


def _should_include_audio_channels(format_key, settings):
    if settings.get("audio_mode", "convert") == "copy":
        return False

    channels_key = str(settings.get("audio_channels", "original"))
    if format_key in LOSSLESS_AUDIO_FORMAT_KEYS and channels_key == "original":
        return False
    return True


def _should_include_audio_normalization(settings):
    return bool(
        settings.get("audio_normalize_streaming", False)
        and settings.get("audio_mode", "convert") != "copy"
    )
