"""Shared FFmpeg utilities used by ConversionTask, MergeTask, and FileProber."""

import logging
import os
import re
import sys


STREAMING_LOUDNORM_FILTER = "loudnorm=I=-16:TP=-1:LRA=7"

VIDEO_CONTAINER_OUTPUTS = ('mp4', 'mkv', 'mov')

# Formats audio dont le conteneur sait embarquer une pochette (attached_pic).
COVER_ART_AUDIO_OUTPUTS = ('mp3', 'aac', 'm4b', 'alac', 'flac')

_WAV_DEPTH_TO_CODEC = {'16': 'pcm_s16le', '24': 'pcm_s24le', '32': 'pcm_f32le'}

# Conteneurs MPEG-TS (flux de diffusion / captures TV, caméscopes AVCHD). Ces
# flux ont souvent des PTS manquants ou des DTS non-monotones ; `-fflags +genpts`
# régénère les PTS manquants à l'entrée (correctif documenté FFmpeg), ce qui
# fiabilise surtout les chemins `-c copy` vers MP4.
# Les captures TV (.mpg d'enregistreurs type adslTV, .vob de DVD) sont en pratique
# des flux MPEG-PS/TS et souffrent des mêmes défauts : on les traite pareil.
TRANSPORT_STREAM_EXTENSIONS = {
    '.ts', '.m2ts', '.mts', '.m2t', '.tp', '.trp', '.mpg', '.mpeg', '.vob',
}

# Analyse d'entrée élargie pour ces captures : les paramètres d'un flux (débit
# d'échantillonnage audio notamment) apparaissent parfois très tard dans le flux.
# Avec les valeurs par défaut, FFmpeg déclare « Could not find codec parameters »
# puis échoue au muxage MP4 (« sample rate not set »). 200 Mo / 60 s d'analyse
# couvrent les captures hertziennes réelles sans coût mesurable sur les fichiers sains.
BROADCAST_PROBESIZE = '200M'
BROADCAST_ANALYZEDURATION = '60M'  # microsecondes = 60 s


def is_transport_stream(path):
    """True si le chemin pointe vers une capture MPEG-TS/PS (par extension)."""
    return os.path.splitext(path or '')[1].lower() in TRANSPORT_STREAM_EXTENSIONS


def broadcast_input_args(path):
    """Options d'entrée à placer avant `-i` pour une capture TV, sinon []."""
    if not is_transport_stream(path):
        return []
    return [
        '-fflags', '+genpts',
        '-probesize', BROADCAST_PROBESIZE,
        '-analyzeduration', BROADCAST_ANALYZEDURATION,
    ]


def _bin_path(executable):
    if getattr(sys, 'frozen', False):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    return os.path.join(base_path, 'bin', executable)



# Le muxeur refuse un flux copié tel quel quand le conteneur n'a pas de tag pour
# son codec : « Could not find tag for codec msmpeg4v3 in stream #0, codec not
# currently supported in container ». Rien n'est écrit, tout le fichier échoue.
_COPY_TAG_ERROR_RE = re.compile(
    r"Could not find tag for codec ([\w.+-]+) in stream #\d+", re.IGNORECASE
)


def detect_uncopyable_streams(stderr_lines, metas, copy_kinds):
    """Quels flux en mode « copie » le conteneur de sortie a-t-il refusés ?

    Renvoie un sous-ensemble de ``copy_kinds`` ({'video', 'audio'}) déduit du
    message du muxeur. Le codec cité est rapproché de ceux des sources (``metas``,
    plusieurs pour une fusion) afin de ne réencoder que le flux fautif ; faute de
    correspondance — ou de métadonnées — on réencode tout ce qui était en copie
    plutôt que d'échouer.
    """
    if not copy_kinds:
        return set()
    codecs = set()
    for line in stderr_lines or ():
        match = _COPY_TAG_ERROR_RE.search(line)
        if match:
            codecs.add(match.group(1).lower())
    if not codecs:
        return set()

    video_codecs = set()
    audio_codecs = set()

    def collect(target, tracks, fallback):
        for track in tracks or ():
            name = str(getattr(track, 'codec_name', '') or '').lower()
            if name:
                target.add(name)
        name = str(fallback or '').lower()
        if name:
            target.add(name)

    for meta in metas or ():
        if meta is None:
            continue
        collect(video_codecs, getattr(meta, 'video_tracks', ()), getattr(meta, 'video_codec', ''))
        collect(audio_codecs, getattr(meta, 'audio_tracks', ()), getattr(meta, 'audio_codec', ''))

    kinds = set()
    for codec in codecs:
        if codec in video_codecs:
            kinds.add('video')
        elif codec in audio_codecs:
            kinds.add('audio')
        else:
            # Codec non rattachable (source non sondée, nom différent côté muxeur) :
            # on ne sait pas lequel est fautif, on réencode tout ce qui était copié.
            return set(copy_kinds)
    return kinds & set(copy_kinds)

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
        mode = settings.get('rate_mode', 'cbr')
        if mode == 'vbr':
            cmd.extend(['-q:a', str(settings.get('audio_qscale', 0))])
        elif mode == 'abr':
            # ABR : débit moyen ciblé (libmp3lame n'a pas de borne min/max VBR).
            cmd.extend(['-abr', '1', '-b:a', settings.get('audio_bitrate', '192k')])
        else:  # cbr
            cmd.extend(['-b:a', settings.get('audio_bitrate', '192k')])
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
