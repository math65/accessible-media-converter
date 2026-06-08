"""Shared FFmpeg utilities used by ConversionTask, MergeTask, and FileProber."""

import logging
import os
import sys


STREAMING_LOUDNORM_FILTER = "loudnorm=I=-16:TP=-1:LRA=7"

VIDEO_CONTAINER_OUTPUTS = ('mp4', 'mkv', 'mov')

# Formats audio dont le conteneur sait embarquer une pochette (attached_pic).
COVER_ART_AUDIO_OUTPUTS = ('mp3', 'aac', 'm4b', 'alac', 'flac')

_WAV_DEPTH_TO_CODEC = {'16': 'pcm_s16le', '24': 'pcm_s24le', '32': 'pcm_f32le'}


def _bin_path(executable):
    if getattr(sys, 'frozen', False):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    return os.path.join(base_path, 'bin', executable)


def get_ffmpeg_path():
    candidate = _bin_path('ffmpeg.exe')
    if os.path.exists(candidate):
        return candidate
    logging.warning("ffmpeg.exe non trouvé dans bin/, utilisation du PATH système")
    return "ffmpeg"


def get_ffprobe_path():
    candidate = _bin_path('ffprobe.exe')
    if os.path.exists(candidate):
        return candidate
    return "ffprobe"


def parse_ffmpeg_threads(settings):
    value = settings.get("ffmpeg_threads", "auto")
    if isinstance(value, str) and value.lower() == "auto":
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return max(1, parsed)


def apply_metadata_preservation(cmd, settings):
    """Ajoute les drapeaux conservant tags globaux et chapitres si l'option est active.

    Renvoie True si la conservation est demandée, pour permettre à l'appelant
    de décider en plus du sort de la pochette (attached_pic).
    """
    if settings.get('preserve_metadata', False):
        cmd.extend(['-map_metadata', '0', '-map_chapters', '0'])
        return True
    return False


def apply_common_audio_options(cmd, settings):
    sample_rate = settings.get('audio_sample_rate', 'original')
    if sample_rate != 'original':
        cmd.extend(['-ar', sample_rate])

    channels = settings.get('audio_channels', 'original')
    if channels == '2':
        cmd.extend(['-ac', '2'])
    elif channels == '1':
        cmd.extend(['-ac', '1'])


def apply_audio_codec_args(cmd, codec_key, settings):
    if codec_key == 'mp3':
        cmd.extend(['-c:a', 'libmp3lame'])
        if settings.get('rate_mode', 'cbr') == 'cbr':
            cmd.extend(['-b:a', settings.get('audio_bitrate', '192k')])
        else:
            cmd.extend(['-q:a', str(settings.get('audio_qscale', 0))])
    elif codec_key == 'aac':
        cmd.extend(['-c:a', 'aac'])
        if settings.get('rate_mode', 'cbr') == 'cbr':
            cmd.extend(['-b:a', settings.get('audio_bitrate', '192k')])
        else:
            cmd.extend(['-q:a', str(settings.get('audio_qscale', 3))])
    elif codec_key == 'opus':
        cmd.extend(['-c:a', 'libopus', '-b:a', settings.get('audio_bitrate', '192k')])
    elif codec_key == 'ogg':
        cmd.extend(['-c:a', 'libvorbis', '-q:a', str(settings.get('audio_qscale', 6))])
    elif codec_key == 'wma':
        cmd.extend(['-c:a', 'wmav2', '-b:a', settings.get('audio_bitrate', '128k')])
    elif codec_key == 'wav':
        depth = settings.get('audio_bit_depth', 'original')
        cmd.extend(['-c:a', _WAV_DEPTH_TO_CODEC.get(str(depth), 'pcm_s16le')])
    elif codec_key == 'flac':
        cmd.extend(['-c:a', 'flac', '-compression_level', str(settings.get('flac_compression', 5))])
        depth = settings.get('audio_bit_depth', 'original')
        if depth == '16':
            cmd.extend(['-sample_fmt', 's16'])
        elif depth == '24':
            cmd.extend(['-sample_fmt', 's32'])
    elif codec_key == 'alac':
        cmd.extend(['-c:a', 'alac'])
        depth = settings.get('audio_bit_depth', 'original')
        if depth == '16':
            cmd.extend(['-sample_fmt', 's16p'])
        elif depth == '24':
            cmd.extend(['-sample_fmt', 's32p'])
