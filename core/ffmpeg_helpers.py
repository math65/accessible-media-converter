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


# ── Annee visible sous Windows ────────────────────────────────────────────────
# Signale sur AppleVis le 2026-08-21 : apres conversion, « the year is missing even
# though the box to preserve full metadata and cover art is checked » — titre, artiste
# et album, eux, s'affichent.
#
# Cause reelle (verifiee en interrogeant le systeme de proprietes de l'Explorateur
# lui-meme, pas une supposition) : Windows lit tres bien l'ID3v2.4, MAIS il n'analyse
# la date que si la valeur vaut « AAAA » ou « AAAA-MM-JJ ». Les fichiers iTunes /
# Apple Music stockent un horodatage ISO complet dans leur tag date
# (« 1998-05-03T07:00:00Z ») ; `-map_metadata 0` le recopie tel quel et l'Explorateur
# renonce, laissant l'annee vide pendant que le reste s'affiche. Meme symptome observe
# avec « 1998/05/03 » ou « (1998) ».
#
# Deux garde-fous complementaires, l'un n'annule pas l'autre :
#   1. normalize_date_tag() ramene la valeur a une forme lisible — seul remede pour les
#      sorties FLAC et WMA, ou l'horodatage brut reste sinon invisible sous Windows ;
#   2. l'ID3v2.3 sur les sorties MP3, ou FFmpeg range l'annee dans TYER (4 chiffres,
#      toujours analysable) au lieu du TDRC libre de l'ID3v2.4 ; c'est aussi ce que
#      produisent LAME et les encodeurs grand public, donc un gain de compatibilite
#      avec les vieux lecteurs. Contrepartie acceptee : une date complete se scinde en
#      TYER + TDAT au lieu d'un TDRC unique.
ID3V2_COMPAT_VERSION = '3'

# Une annee sur 4 chiffres, eventuellement suivie d'un mois et d'un jour quel que soit
# le separateur. Volontairement permissif : on cherche a recuperer l'annee, pas a
# valider une date.
_DATE_VALUE_RE = re.compile(r'(\d{4})(?:[-/.](\d{1,2})[-/.](\d{1,2}))?')
_WINDOWS_READABLE_DATE_RE = re.compile(r'^\d{4}(-\d{2}-\d{2})?$')
_YEAR_ONLY_RE = re.compile(r'^\d{4}$')


# Le FLAC est le plus exigeant des conteneurs qu'on produit : Windows n'affiche son
# annee que si le commentaire Vorbis DATE vaut exactement « AAAA » — meme un
# « 1998-05-03 » parfaitement valide laisse la colonne vide. Les autres (MP3, M4A,
# M4B, OGG) acceptent la date complete. On ne reduit donc a l'annee seule que la ou
# c'est necessaire, pour ne pas jeter le mois et le jour partout ailleurs.
YEAR_ONLY_OUTPUT_FORMATS = ('flac',)

# Conteneurs ASF : l'annee passe par l'attribut natif WM/Year (voir plus bas).
ASF_YEAR_OUTPUT_FORMATS = ('wma',)


def normalize_date_tag(value, year_only=False):
    """Ramene une date de tag a « AAAA-MM-JJ », ou a « AAAA » si year_only.

    Renvoie None quand il n'y a rien a faire : valeur deja lisible telle quelle, vide,
    ou sans annee identifiable (on prefere alors laisser la valeur d'origine intacte
    plutot que d'inventer une date).
    """
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not value:
        return None
    if value == value[:4] and _YEAR_ONLY_RE.match(value):
        return None
    if not year_only and _WINDOWS_READABLE_DATE_RE.match(value):
        return None
    match = _DATE_VALUE_RE.search(value)
    if not match:
        return None
    year, month, day = match.groups()
    if month and day and not year_only:
        return f"{year}-{int(month):02d}-{int(day):02d}"
    return year


def date_tag_year(value):
    """Annee sur 4 chiffres contenue dans une date de tag, ou None."""
    if not isinstance(value, str):
        return None
    match = _DATE_VALUE_RE.search(value.strip())
    return match.group(1) if match else None


def apply_date_tag_compat(cmd, meta, target_format=None):
    """Reecrit le tag date herite de la source s'il est illisible pour Windows.

    A placer apres `-map_metadata 0` (la derniere occurrence de `-metadata` gagne) et
    avant les tags edites par l'utilisateur, qui doivent rester prioritaires.
    """
    tags = getattr(meta, 'format_tags', None) or {}
    raw = tags.get('date') or tags.get('year')
    normalized = normalize_date_tag(
        raw, year_only=target_format in YEAR_ONLY_OUTPUT_FORMATS
    )
    if normalized:
        cmd.extend(['-metadata', f'date={normalized}'])

    if target_format in ASF_YEAR_OUTPUT_FORMATS:
        # L'ASF est un cas a part : Windows n'y lit pas le tag `date` generique de
        # FFmpeg, seulement l'attribut natif WM/Year. Sans lui l'annee d'un WMA reste
        # invisible quelle que soit sa valeur — verifie, y compris avec un simple
        # « 1998 ». On ecrit les deux : `date` pour les lecteurs tiers, WM/Year pour
        # l'Explorateur.
        year = date_tag_year(normalized or raw)
        if year:
            cmd.extend(['-metadata', f'WM/Year={year}'])


def apply_id3v2_compat_args(cmd, output_path):
    """Force l'ID3v2.3 sur les sorties MP3.

    C'est une option privee du muxeur mp3 : elle doit etre placee avant le fichier de
    sortie, et ne doit surtout pas etre emise pour un autre conteneur (FFmpeg refuse
    l'option inconnue et toute la commande echoue).
    """
    if os.path.splitext(output_path or '')[1].lower() == '.mp3':
        cmd.extend(['-id3v2_version', ID3V2_COMPAT_VERSION])


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


# --- Sous-titres tx3g : silences trop longs pour le conteneur MP4 -----------
#
# Le muxeur MP4 range les sous-titres tx3g dans une base de temps en
# MICROSECONDES et comble chaque silence entre deux répliques par un échantillon
# vide. Passé la capacité d'un entier 32 bits, il refuse cet échantillon
# (« Packet duration: N / dts: N in stream X is out of range ») **et cesse
# d'écrire l'audio du fichier**, tout en terminant en code 0 avec une vidéo
# complète et un index valide. Symptôme : un film parfait à l'image, muet après
# quelques secondes, qu'aucun contrôle de durée global ne détecte (la durée d'un
# conteneur est celle de son flux le plus long).
#
# Mesures (FFmpeg 9.0.1 embarqué) : le refus apparaît dès ~2148 s de silence
# (INT32_MAX µs) ; l'audio, lui, survit encore à 4350 s et disparaît à 4662 s
# (cas réel) comme à 4700 s. Le seuil exact de la perte audio n'a pas été
# cerné — on ne s'y fie donc pas : la détection s'appuie sur le refus réel du
# muxeur, jamais sur une durée devinée (même principe que le repli de copie).
# Autres conditions observées : l'audio doit être RÉENCODÉ (en `-c:a copy` rien
# ne casse) et le silence doit tomber pendant que l'audio coule encore.
#
# FFmpeg 9.0.2 (septembre 2026) corrige la perte de l'audio : le muxeur refuse
# toujours l'échantillon (la réplique tardive est perdue) mais l'audio est
# complet, le filet ci-dessous ne se déclenche donc plus. On le garde : il ne
# coûte rien quand tout va bien et protège d'une régression amont.
#
# Cas réel (août 2026) : quatre films d'un utilisateur, tous de plus de 71 min,
# dont un sous-titre « forcé » ne portait que trois répliques (12 s, 100 s, puis
# 4767 s) — un silence de 4662 s. Reproduit à 10 Ko près sur 9,9 Go.
#
# La base de temps des pistes tx3g est imposée par FFmpeg (`-enc_time_base` n'a
# aucun effet) et relire les temps des sous-titres coûte une lecture complète du
# fichier (51 s sur 10 Go, intenable sur un lot). On s'appuie donc sur le message
# du muxeur, qui nomme lui-même le flux de SORTIE fautif : gratuit et sûr.
_OVERSIZED_SUBTITLE_RE = re.compile(r"in stream (\d+) is out of range")


def parse_oversized_subtitle_stream(line):
    """Index du flux de SORTIE refusé par le muxeur, ou None."""
    match = _OVERSIZED_SUBTITLE_RE.search(line or "")
    if not match:
        return None
    try:
        return int(match.group(1))
    except (TypeError, ValueError):
        return None


def detect_oversized_subtitle_streams(stderr_lines):
    """Indices des flux de sortie que le muxeur a refusés (voir ci-dessus)."""
    found = set()
    for line in stderr_lines or ():
        index = parse_oversized_subtitle_stream(line)
        if index is not None:
            found.add(index)
    return found
