import builtins
import os

from core.i18n import AUTO_LANGUAGE_CODE, normalize_ui_language


AUDIO_OUTPUT_FORMAT_KEYS = ("mp3", "aac", "wav", "flac", "alac", "ogg", "wma")
VIDEO_OUTPUT_FORMAT_KEYS = ("mp4", "mkv", *AUDIO_OUTPUT_FORMAT_KEYS)
VIDEO_CONTAINER_FORMAT_KEYS = ("mp4", "mkv")
LOSSLESS_AUDIO_FORMAT_KEYS = ("wav", "flac", "alac")
CONTAINER_AUDIO_CODEC_OPTIONS = {
    "mp4": ("aac", "mp3"),
    "mkv": ("aac", "mp3", "opus", "flac"),
}
VIDEO_PRESET_PROFILE_SETTINGS = {
    "compatible": {
        "video_crf": 23,
        "video_encoder_preset": "medium",
        "video_profile": "high",
        "video_pixel_format": "yuv420p",
    },
    "balanced": {
        "video_crf": 22,
        "video_encoder_preset": "medium",
        "video_profile": "high",
        "video_pixel_format": "yuv420p",
    },
    "high_quality": {
        "video_crf": 18,
        "video_encoder_preset": "slow",
        "video_profile": "high",
        "video_pixel_format": "yuv420p",
    },
    "small_file": {
        "video_crf": 28,
        "video_encoder_preset": "medium",
        "video_profile": "high",
        "video_pixel_format": "yuv420p",
    },
    "fast_encode": {
        "video_crf": 23,
        "video_encoder_preset": "veryfast",
        "video_profile": "high",
        "video_pixel_format": "yuv420p",
    },
}
VALID_VIDEO_PRESET_PROFILE_KEYS = (*VIDEO_PRESET_PROFILE_SETTINGS.keys(), "custom")
VALID_VIDEO_ENCODER_PRESETS = ("veryfast", "fast", "medium", "slow")
VALID_VIDEO_PROFILES = ("baseline", "main", "high")
VALID_VIDEO_PIXEL_FORMATS = ("yuv420p", "yuv444p")
VALID_OUTPUT_MODES = ("source", "custom", "ask")
VALID_EXISTING_OUTPUT_POLICIES = ("rename", "overwrite", "skip")
MIN_CONCURRENT_JOBS = 1
MAX_CONCURRENT_JOBS = 4
DEFAULT_CONCURRENT_JOBS = 2
DEFAULT_FFMPEG_THREADS = "auto"


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
        "video_preset_profile": "balanced",
        "video_crf": 22,
        "video_encoder_preset": "medium",
        "video_profile": "high",
        "video_pixel_format": "yuv420p",
        "audio_mode": "convert",
        "audio_codec": "aac",
        "audio_normalize_streaming": False,
        "rate_mode": "cbr",
        "audio_bitrate": "192k",
        "audio_qscale": 3,
        "audio_sample_rate": "original",
        "audio_channels": "2",
    },
    "mkv": {
        "video_mode": "convert",
        "video_preset_profile": "balanced",
        "video_crf": 22,
        "video_encoder_preset": "medium",
        "video_profile": "high",
        "video_pixel_format": "yuv420p",
        "audio_mode": "convert",
        "audio_codec": "aac",
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
    "support_user_email": "",
    "existing_output_policy": "rename",
    "open_output_folder_after_batch": False,
    "max_concurrent_jobs": DEFAULT_CONCURRENT_JOBS,
    "ffmpeg_threads": DEFAULT_FFMPEG_THREADS,
    "continue_on_error": True,
    "check_updates_on_startup": True,
    "ui_language": AUTO_LANGUAGE_CODE,
    "debug_enabled": False,
    "session_restore_pending": False,
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


def get_container_audio_codec_options(format_key):
    return CONTAINER_AUDIO_CODEC_OPTIONS.get(format_key, ())


def get_audio_codec_label(codec_key):
    labels = {
        "aac": _translate("AAC"),
        "mp3": _translate("MP3"),
        "opus": _translate("Opus"),
        "flac": _translate("FLAC"),
        "wav": "WAV",
        "alac": "ALAC",
        "ogg": "OGG",
        "wma": "WMA",
    }
    return labels.get(codec_key, str(codec_key or "").upper())


def get_effective_audio_codec(format_key, settings):
    if format_key == "mov":
        return str(settings.get("audio_codec", "aac") or "aac").lower()
    if format_key in VIDEO_CONTAINER_FORMAT_KEYS:
        default_codec = DEFAULT_FORMAT_SETTINGS[format_key]["audio_codec"]
        allowed_codecs = get_container_audio_codec_options(format_key)
        codec = str(settings.get("audio_codec", default_codec) or default_codec).lower()
        if codec in allowed_codecs:
            return codec
        return default_codec
    return format_key


def get_video_preset_definition(preset_key):
    return VIDEO_PRESET_PROFILE_SETTINGS.get(preset_key)


def apply_video_preset_profile(settings, preset_key):
    updated = dict(settings)
    preset_definition = get_video_preset_definition(preset_key)
    if not preset_definition:
        return updated
    updated.update(preset_definition)
    updated["video_preset_profile"] = preset_key
    return updated


def get_matching_video_preset_profile(settings):
    for preset_key, preset_definition in VIDEO_PRESET_PROFILE_SETTINGS.items():
        if all(settings.get(field_name) == expected_value for field_name, expected_value in preset_definition.items()):
            return preset_key
    return None


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
    if format_key in VIDEO_CONTAINER_FORMAT_KEYS:
        normalized = _normalize_container_video_settings(format_key, normalized)
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
    normalized["check_updates_on_startup"] = bool(
        normalized.get("check_updates_on_startup", APP_DEFAULT_SETTINGS["check_updates_on_startup"])
    )
    normalized["ui_language"] = normalize_ui_language(
        normalized.get("ui_language", APP_DEFAULT_SETTINGS["ui_language"])
    )
    normalized["session_restore_pending"] = bool(
        normalized.get("session_restore_pending", APP_DEFAULT_SETTINGS["session_restore_pending"])
    )
    normalized["debug_restore_pending"] = bool(
        normalized.get("debug_restore_pending", APP_DEFAULT_SETTINGS["debug_restore_pending"])
    )
    normalized["max_concurrent_jobs"] = _normalize_concurrent_jobs(
        normalized.get("max_concurrent_jobs", APP_DEFAULT_SETTINGS["max_concurrent_jobs"])
    )
    normalized["ffmpeg_threads"] = _normalize_ffmpeg_threads(
        normalized.get("ffmpeg_threads", APP_DEFAULT_SETTINGS["ffmpeg_threads"])
    )

    return normalized


def _normalize_concurrent_jobs(value):
    try:
        jobs = int(value)
    except (TypeError, ValueError):
        jobs = DEFAULT_CONCURRENT_JOBS
    return min(max(jobs, MIN_CONCURRENT_JOBS), MAX_CONCURRENT_JOBS)


def get_detected_cpu_threads():
    try:
        detected = int(os.cpu_count() or 1)
    except (TypeError, ValueError):
        detected = 1
    return max(1, detected)


def get_ffmpeg_thread_values():
    return tuple(range(1, get_detected_cpu_threads() + 1))


def _normalize_ffmpeg_threads(value):
    if isinstance(value, str) and value.lower() == DEFAULT_FFMPEG_THREADS:
        return DEFAULT_FFMPEG_THREADS

    try:
        threads = int(value)
    except (TypeError, ValueError):
        return DEFAULT_FFMPEG_THREADS

    return min(max(threads, 1), get_detected_cpu_threads())


def _normalize_container_video_settings(format_key, settings):
    normalized = dict(settings)
    normalized["video_crf"] = _normalize_video_crf_value(
        normalized.get("video_crf", DEFAULT_FORMAT_SETTINGS[format_key]["video_crf"]),
        default_value=DEFAULT_FORMAT_SETTINGS[format_key]["video_crf"],
    )

    if normalized.get("video_encoder_preset") not in VALID_VIDEO_ENCODER_PRESETS:
        normalized["video_encoder_preset"] = DEFAULT_FORMAT_SETTINGS[format_key]["video_encoder_preset"]
    if normalized.get("video_profile") not in VALID_VIDEO_PROFILES:
        normalized["video_profile"] = DEFAULT_FORMAT_SETTINGS[format_key]["video_profile"]
    if normalized.get("video_pixel_format") not in VALID_VIDEO_PIXEL_FORMATS:
        normalized["video_pixel_format"] = DEFAULT_FORMAT_SETTINGS[format_key]["video_pixel_format"]

    normalized["audio_codec"] = get_effective_audio_codec(format_key, normalized)

    requested_preset = str(normalized.get("video_preset_profile", "") or "").strip()
    matched_preset = get_matching_video_preset_profile(normalized)

    if matched_preset:
        normalized["video_preset_profile"] = matched_preset
    elif requested_preset == "custom":
        normalized["video_preset_profile"] = "custom"
    elif requested_preset in VIDEO_PRESET_PROFILE_SETTINGS:
        normalized["video_preset_profile"] = "custom"
    else:
        normalized["video_preset_profile"] = DEFAULT_FORMAT_SETTINGS[format_key]["video_preset_profile"]

    return normalized


def _normalize_video_crf_value(value, default_value):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default_value

    if 0 <= parsed <= 51:
        return parsed
    return default_value


def build_format_summary(format_key, settings):
    if format_key in VIDEO_CONTAINER_FORMAT_KEYS:
        return _build_video_summary(format_key, settings)
    return _build_audio_summary(format_key, settings, include_channels=True)


def _build_video_summary(format_key, settings):
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
        audio_parts = [_build_audio_mode_summary(format_key, settings, include_codec_label=True)]
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


def _build_audio_mode_summary(format_key, settings, include_codec_label=False):
    codec_key = get_effective_audio_codec(format_key, settings)
    codec_label = get_audio_codec_label(codec_key)
    if settings.get("audio_mode", "convert") == "copy":
        return _translate("Copy")

    if codec_key in LOSSLESS_AUDIO_FORMAT_KEYS:
        if include_codec_label:
            return f"{codec_label} {_translate('Lossless')}"
        return _translate("Lossless")

    if codec_key == "opus":
        bitrate = settings.get("audio_bitrate", "192k")
        if include_codec_label:
            return f"{codec_label} {bitrate}"
        return _translatef("Bitrate {bitrate}", bitrate=bitrate)

    if settings.get("rate_mode", "cbr") == "vbr":
        quality = settings.get(
            "audio_qscale",
            DEFAULT_FORMAT_SETTINGS.get(codec_key, DEFAULT_FORMAT_SETTINGS["mp3"]).get(
                "audio_qscale", 0
            ),
        )
        summary = _translatef("VBR Q{quality}", quality=quality)
    else:
        bitrate = settings.get(
            "audio_bitrate",
            DEFAULT_FORMAT_SETTINGS.get(codec_key, DEFAULT_FORMAT_SETTINGS["mp3"]).get(
                "audio_bitrate", "192k"
            ),
        )
        summary = _translatef("CBR {bitrate}", bitrate=bitrate)

    if include_codec_label:
        return f"{codec_label} {summary}"
    return summary


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
