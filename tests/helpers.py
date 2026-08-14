"""Outils partagés par les tests.

Les tests portent sur `core/` uniquement : aucune dépendance à wxPython, donc
aucune fenêtre ouverte pendant l'exécution. Les modules de `core/` traduisent via
un `_()` optionnel (voir `_translate`), il n'y a donc rien à installer pour eux.
"""

import os
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from core.ffmpeg_helpers import get_ffmpeg_path, get_ffprobe_path  # noqa: E402
from core.probe import MediaMetadata, MediaTrack  # noqa: E402


def ffmpeg_available():
    return os.path.isfile(get_ffmpeg_path())


def run_ffmpeg(args):
    """Lance le FFmpeg embarqué ; lève si la commande échoue."""
    subprocess.run(
        [get_ffmpeg_path(), '-y', '-v', 'error'] + args,
        check=True, capture_output=True, timeout=120,
    )


def probe_stream_types(path):
    """['video', 'audio', ...] dans l'ordre des flux du fichier."""
    result = subprocess.run(
        [
            get_ffprobe_path(), '-v', 'error',
            '-show_entries', 'stream=codec_type',
            '-of', 'default=noprint_wrappers=1:nokey=1', path,
        ],
        capture_output=True, text=True, check=True, timeout=60,
    )
    return result.stdout.split()


def probe_tags(path):
    result = subprocess.run(
        [
            get_ffprobe_path(), '-v', 'error',
            '-show_entries', 'format_tags',
            '-of', 'default=noprint_wrappers=1', path,
        ],
        capture_output=True, text=True, check=True, timeout=60,
    )
    tags = {}
    for line in result.stdout.splitlines():
        if '=' in line:
            key, value = line.split('=', 1)
            tags[key.replace('TAG:', '').lower()] = value
    return tags


def make_media(path="D:/fixtures/movie.mp4", video=(), audio=(), subtitle=()):
    """MediaMetadata en mémoire, sans sonde : (index, ...) → pistes."""
    meta = MediaMetadata(path)
    meta.video_tracks = list(video)
    meta.audio_tracks = list(audio)
    meta.subtitle_tracks = list(subtitle)
    meta.has_video = bool(video)
    meta.duration = 60.0
    return meta


def video_track(index):
    return MediaTrack(index, 'video', 'h264')


def audio_track(index, sample_rate=48000, language='und'):
    return MediaTrack(index, 'audio', 'aac', language=language, sample_rate=sample_rate)


def subtitle_track(index, codec_name='subrip'):
    return MediaTrack(index, 'subtitle', codec_name)


def mapped_streams(cmd):
    """Indices demandés par les `-map` d'une commande FFmpeg construite."""
    return [cmd[i + 1] for i, token in enumerate(cmd) if token == '-map']
