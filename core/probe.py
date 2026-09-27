import os
import subprocess
import json
import logging
import builtins

from core.cue import finalize_tracks, load_cue_file, resolve_cue_audio
from core.ffmpeg_helpers import broadcast_input_args, get_ffprobe_path, is_transport_stream
from core.track_settings import is_ui_track_visible

FFPROBE_TIMEOUT_SECONDS = 30
# Les captures TV sont sondées avec un probesize élargi : lire plusieurs
# centaines de Mo depuis un disque lent demande plus que le délai standard.
FFPROBE_BROADCAST_TIMEOUT_SECONDS = 120


# Seuil de détection d'une piste anormalement courte : une piste dont la durée
# est inférieure à ce ratio de celle du conteneur est signalée. Volontairement
# permissif — un générique de fin muet ou une piste d'audiodescription qui
# s'arrête un peu avant la fin sont légitimes ; on ne vise que les amputations
# franches (une piste à 17 s sur un film d'1 h 19, soit 0,4 %).
SHORT_TRACK_RATIO = 0.5
# En deçà de cette durée de conteneur, le ratio n'a pas de sens (jingles,
# fichiers de test) : on ne contrôle rien.
SHORT_TRACK_MIN_CONTAINER_DURATION = 30.0


def _format_duration(seconds):
    """hh:mm:ss lisible dans le journal ; '?' si inconnue."""
    if seconds is None:
        return "?"
    try:
        total = int(round(float(seconds)))
    except (TypeError, ValueError):
        return "?"
    return f"{total // 3600:02d}:{(total % 3600) // 60:02d}:{total % 60:02d}"


def parse_stream_duration(stream):
    """Durée d'un flux ffprobe en secondes, ou None si le format ne la porte pas.

    Trois sources, par ordre de fiabilité :
      1. `duration` — présent en MP4/MOV, calculé depuis la table d'échantillons ;
      2. `duration_ts` x `time_base` — même information, quand seule la forme
         entière est exposée ;
      3. le tag `DURATION` — **le seul disponible en Matroska**, qui ne stocke
         aucune durée par piste dans ses en-têtes, au format `HH:MM:SS.nnnnnnnnn`.

    Sans le point 3, tout MKV renverrait None et échapperait au contrôle.
    """
    if not isinstance(stream, dict):
        return None

    try:
        value = float(stream.get('duration'))
        if value > 0:
            return value
    except (TypeError, ValueError):
        pass

    try:
        ticks = float(stream.get('duration_ts'))
        numerator, _, denominator = str(stream.get('time_base', '')).partition('/')
        scale = float(numerator) / float(denominator)
        value = ticks * scale
        if value > 0:
            return value
    except (TypeError, ValueError, ZeroDivisionError):
        pass

    tags = stream.get('tags') or {}
    if isinstance(tags, dict):
        for key, raw in tags.items():
            if str(key).lower() != 'duration':
                continue
            try:
                hours, minutes, seconds = str(raw).split(':')
                value = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
                if value > 0:
                    return value
            except (TypeError, ValueError):
                pass
    return None


def find_short_tracks(meta, ratio=SHORT_TRACK_RATIO):
    """Pistes dont la durée est nettement inférieure à celle du conteneur.

    Renvoie une liste de (track, duration, container_duration). C'est le signal
    qui manquait pour l'affaire des MP4 à l'audio amputé : la durée du conteneur
    est celle du flux le PLUS LONG, donc un fichier dont la vidéo est complète
    mais dont l'audio meurt en route paraît intact à tout contrôle global.

    Les pistes de durée inconnue (Matroska sans tag) ne sont jamais signalées :
    en l'absence de mesure, aucun soupçon.
    """
    container = getattr(meta, 'duration', 0) or 0
    if container < SHORT_TRACK_MIN_CONTAINER_DURATION:
        return []

    findings = []
    for track in list(getattr(meta, 'audio_tracks', []) or []):
        duration = getattr(track, 'duration', None)
        if duration is None:
            continue
        if track.is_attached_pic():
            continue
        if duration < container * ratio:
            findings.append((track, duration, container))
    return findings


def _translate(msgid):
    translator = builtins.__dict__.get('_')
    if callable(translator):
        return translator(msgid)
    return msgid


def _translatef(msgid, **kwargs):
    return _translate(msgid).format(**kwargs)

class MediaTrack:
    def __init__(self, stream_index, codec_type, codec_name, language='und', title=None,
                 disposition=None, sample_rate=None, duration=None):
        self.index = stream_index
        self.codec_type = codec_type
        self.codec_name = codec_name
        self.language = language
        self.title = title
        self.disposition = disposition if disposition else {}
        # Débit d'échantillonnage (audio) tel que rapporté par ffprobe. Absent
        # quand ffprobe n'a pas pu lire les paramètres du flux (capture TV
        # abîmée) : voir is_usable().
        self.sample_rate = sample_rate
        # Durée du FLUX (secondes), distincte de celle du conteneur. None quand
        # le format ne la porte pas — c'est le cas courant en Matroska, où elle
        # n'existe que sous forme de tag optionnel. Ne jamais confondre None
        # (inconnue) avec 0 (vide) : seule la première interdit tout contrôle.
        self.duration = duration

    def is_usable(self):
        """False si FFmpeg n'a pas pu déterminer les paramètres du flux.

        Un flux audio sans débit d'échantillonnage (« Could not find codec
        parameters … unspecified sample rate ») est refusé par le muxeur MP4 au
        moment d'écrire l'en-tête, ce qui fait échouer TOUT le fichier. On le
        détecte à la sonde pour l'écarter du mapping par défaut."""
        if self.codec_type == 'audio':
            return bool(self.sample_rate)
        return True

    def is_default(self): return self.disposition.get('default', 0) == 1
    def is_forced(self): return self.disposition.get('forced', 0) == 1
    def is_attached_pic(self): return self.disposition.get('attached_pic', 0) == 1
    def is_hidden_from_ui(self): return not is_ui_track_visible(self)

    def get_summary(self):
        parts = [self.codec_name.upper()]
        if self.language and self.language != 'und': parts.append(self.language.upper())
        if self.title: parts.append(f"\"{self.title}\"")
        return " - ".join(parts)

class MediaMetadata:
    def __init__(self, path):
        self.full_path = path
        self.filename = os.path.basename(path)
        # Sous-dossier relatif à la racine ajoutée (vide si fichier ajouté seul).
        # Sert à recréer l'arborescence d'origine sous un dossier de sortie
        # personnalisé quand la préférence preserve_folder_structure est active.
        self.relative_dir = ""
        self.duration = 0
        self.size_bytes = 0
        self.video_tracks = []
        self.audio_tracks = []
        self.subtitle_tracks = []
        self.video_codec = ""
        self.audio_codec = ""
        self.width = 0
        self.height = 0
        self.has_video = False
        self.is_image = False
        self.track_settings = None
        self.audio_extract_track = None
        self.format_tags = {}
        # Pistes audio dont la durée est nettement inférieure à celle du
        # conteneur : liste de (track, duration, container_duration). Renseignée
        # par la sonde, consommée par l'UI pour prévenir AVANT la conversion.
        self.short_audio_tracks = []
        self.has_cover_art = False
        # Indices source des pochettes (flux attached_pic). Le re-tag sur place
        # retire CES flux-là et eux seuls : « tous les flux vidéo » emportait la
        # piste vidéo d'un film avec sa pochette.
        self.cover_stream_indices = []
        # Nombre TOTAL de flux vidéo du fichier (pochettes et flux masqués de
        # l'UI compris) : sert à situer une pochette ajoutée après eux.
        self.video_stream_count = 0
        self.metadata_overrides = None
        # Override de sortie par fichier : {"format": fmt_key, "settings": {...}}.
        # Quand présent, ce fichier est converti avec ce format/qualité au lieu du global.
        self.output_override = None
        # Découpage cue : si cue_sheet (core.cue.CueSheet) est posé, ce media est une
        # image album à découper en N pistes. has_embedded_cue signale un cuesheet
        # intégré (FLAC) que l'utilisateur peut activer ; cue_error = message d'ajout.
        self.cue_sheet = None
        self.has_embedded_cue = False
        self.embedded_cue_text = None
        self.embedded_chapters = None
        self.cue_error = None
        self.source_format_name = ""

    @property
    def has_audio(self): return len(self.audio_tracks) > 0
    @property
    def has_subtitles(self): return len(self.subtitle_tracks) > 0

    def get_audio_track_by_index(self, original_index):
        for track in self.audio_tracks:
            if track.index == original_index:
                return track
        return None

    def get_default_audio_track(self):
        # Une piste illisible ferait échouer l'extraction : on ne la propose
        # jamais d'office (l'utilisateur peut toujours la choisir explicitement).
        usable_tracks = [track for track in self.audio_tracks if track.is_usable()]
        candidates = usable_tracks or self.audio_tracks
        for track in candidates:
            if track.is_default():
                return track
        if candidates:
            return candidates[0]
        return None

    def get_preferred_audio_track(self, preferred_index=None):
        if preferred_index is not None:
            preferred_track = self.get_audio_track_by_index(preferred_index)
            if preferred_track is not None:
                return preferred_track
        return self.get_default_audio_track()

    def get_summary(self):
        if self.is_image:
            parts = []
            if self.width and self.height:
                parts.append(f"{self.width}x{self.height}")
            if self.video_codec:
                parts.append(self.video_codec.upper())
            return " / ".join(parts) if parts else _translate("Image")

        v_info = ""
        if self.video_tracks:
            v = self.video_tracks[0]
            v_info = f"{v.codec_name.upper()}"
            if self.width and self.height: v_info += f" ({self.width}x{self.height})"

        a_info = ""
        count_a = len(self.audio_tracks)
        if count_a > 0:
            a = self.audio_tracks[0]
            if count_a > 1: a_info = _translatef("{count}x Audio", count=count_a)
            else: a_info = a.codec_name.upper()

        s_info = ""
        count_s = len(self.subtitle_tracks)
        if count_s > 0: s_info = _translatef("{count}x Subtitles", count=count_s)

        parts = [x for x in [v_info, a_info, s_info] if x]
        return " / ".join(parts)

class FileProber:
    def __init__(self):
        pass

    def analyze(self, file_path):
        meta = MediaMetadata(file_path)

        if not os.path.exists(file_path):
            logging.error("Fichier introuvable : %s", file_path)
            return meta

        meta.size_bytes = os.path.getsize(file_path)

        if os.path.splitext(file_path)[1].lower() == '.cue':
            return self._analyze_cue(meta, file_path)

        ffprobe = get_ffprobe_path()

        cmd = [ffprobe, '-v', 'quiet']
        # Captures TV : même analyse élargie qu'à la conversion, sinon l'UI et
        # FFmpeg ne voient pas les mêmes pistes.
        cmd.extend(broadcast_input_args(file_path))
        cmd.extend([
            '-print_format', 'json',
            '-show_format',
            '-show_streams',
            '-show_chapters',
            file_path,
        ])

        try:
            output = subprocess.check_output(
                cmd,
                startupinfo=self._get_startup_info(),
                timeout=(
                    FFPROBE_BROADCAST_TIMEOUT_SECONDS
                    if is_transport_stream(file_path)
                    else FFPROBE_TIMEOUT_SECONDS
                ),
            )
            data = json.loads(output)

            fmt = data.get('format', {})
            try:
                meta.duration = float(fmt.get('duration', 0))
            except (TypeError, ValueError):
                meta.duration = 0

            meta.source_format_name = str(fmt.get('format_name', '') or '')
            format_tags = fmt.get('tags', {})
            if isinstance(format_tags, dict):
                meta.format_tags = {
                    str(key).lower(): value for key, value in format_tags.items()
                }

            for stream in data.get('streams', []):
                idx = stream.get('index')
                c_type = stream.get('codec_type')
                c_name = stream.get('codec_name', 'unknown')
                tags = stream.get('tags', {})
                lang = tags.get('language', 'und')
                title = tags.get('title', None)
                disposition = stream.get('disposition', {})

                track = MediaTrack(
                    idx, c_type, c_name, lang, title, disposition,
                    sample_rate=self._parse_sample_rate(stream),
                    duration=parse_stream_duration(stream),
                )

                if c_type == 'video':
                    meta.video_stream_count += 1
                if c_type == 'video' and disposition.get('attached_pic', 0) == 1:
                    meta.has_cover_art = True
                    meta.cover_stream_indices.append(idx)

                if c_type == 'video':
                    if not track.is_hidden_from_ui():
                        meta.video_tracks.append(track)
                        meta.has_video = True
                        if meta.width == 0:
                            meta.width = stream.get('width', 0)
                            meta.height = stream.get('height', 0)
                            meta.video_codec = c_name

                elif c_type == 'audio':
                    if not track.is_hidden_from_ui():
                        meta.audio_tracks.append(track)
                        if not meta.audio_codec:
                            meta.audio_codec = c_name

                elif c_type == 'subtitle':
                    if not track.is_hidden_from_ui():
                        meta.subtitle_tracks.append(track)

            meta.is_image = self._detect_image(meta, fmt)
            if meta.is_image:
                meta.has_video = False
            else:
                self._detect_embedded_cue(meta, data)
                self._log_probe_result(meta)

        except subprocess.TimeoutExpired:
            logging.error("ffprobe timeout (%ss) on %s", FFPROBE_TIMEOUT_SECONDS, file_path)
        except Exception:
            logging.exception("Erreur fatale probing %s", file_path)

        return meta

    @staticmethod
    def _parse_sample_rate(stream):
        """Débit d'échantillonnage en Hz, ou None si absent/illisible."""
        try:
            value = int(stream.get('sample_rate', 0) or 0)
        except (TypeError, ValueError):
            return None
        return value or None

    def _analyze_cue(self, meta, cue_path):
        """Sonde un fichier .cue : parse le cue, résout l'image audio et la sonde
        pour la durée totale, puis attache le CueSheet (toujours, même en erreur,
        pour que la ligne soit reconnue comme une ligne album)."""
        try:
            sheet = load_cue_file(cue_path)
        except Exception:
            logging.exception("Échec du parsing du cue : %s", cue_path)
            meta.cue_error = _translate("This cue sheet could not be read.")
            return meta

        meta.cue_sheet = sheet

        if sheet.multi_file:
            # Cas courant : un cue décrivant un album déjà découpé (un FILE par
            # piste). Il n'y a rien à découper — on l'explique au lieu de laisser
            # croire à une limitation temporaire.
            meta.cue_error = _translate(
                "This cue sheet references several audio files, so there is nothing to split. "
                "Add the audio files themselves instead."
            )
            return meta
        if not sheet.tracks:
            meta.cue_error = _translate("This cue sheet contains no tracks.")
            return meta

        audio_path = resolve_cue_audio(cue_path, sheet.audio_ref)
        if not audio_path:
            meta.cue_error = _translatef(
                "Audio file referenced by the cue sheet not found: {name}",
                name=sheet.audio_ref or "?",
            )
            return meta

        # Sonde l'image audio réelle (réutilise le chemin ffprobe normal) pour la
        # durée totale et le codec ; on garde full_path = le .cue pour l'affichage.
        audio_meta = self.analyze(audio_path)
        meta.duration = audio_meta.duration
        meta.audio_codec = audio_meta.audio_codec
        meta.audio_tracks = audio_meta.audio_tracks
        meta.source_format_name = audio_meta.source_format_name

        sheet.audio_ref = audio_path  # chemin absolu résolu, consommé par le batch
        finalize_tracks(sheet.tracks, int(round((meta.duration or 0) * 1000)))
        return meta

    def _log_probe_result(self, meta):
        """Trace le résultat de la sonde : une ligne par fichier, le détail
        piste par piste uniquement si une durée s'écarte de celle du conteneur.

        Le journal reste lisible sur un lot de 464 fichiers tout en portant, là
        où ça compte, l'information qu'aucun en-tête FFmpeg n'affiche : la durée
        de chaque piste.
        """
        try:
            logging.info(
                "Sonde : %s — conteneur %s, %d vidéo / %d audio / %d sous-titres",
                meta.filename,
                _format_duration(meta.duration),
                len(meta.video_tracks),
                len(meta.audio_tracks),
                len(meta.subtitle_tracks),
            )

            short_tracks = find_short_tracks(meta)
            if not short_tracks:
                return

            meta.short_audio_tracks = short_tracks
            logging.warning(
                "Sonde : %s — %d piste(s) audio anormalement courte(s) par rapport au conteneur (%s).",
                meta.filename,
                len(short_tracks),
                _format_duration(meta.duration),
            )
            for track in meta.audio_tracks:
                duration = getattr(track, 'duration', None)
                logging.warning(
                    "  piste #%s (%s, %s) : %s",
                    track.index,
                    track.codec_name,
                    track.language or 'und',
                    _format_duration(duration) if duration is not None else "durée inconnue",
                )
        except Exception:
            # Le journal ne doit jamais faire échouer une analyse.
            logging.exception("Échec de la journalisation de la sonde")

    def _detect_embedded_cue(self, meta, data):
        """Signale un cue sheet embarqué : tag CUESHEET (texte, EAC/foobar) ou
        chapitres ffprobe (bloc CUESHEET natif FLAC). Découpage opt-in côté UI."""
        cue_text = meta.format_tags.get('cuesheet')
        if isinstance(cue_text, str) and 'TRACK' in cue_text.upper():
            meta.has_embedded_cue = True
            meta.embedded_cue_text = cue_text
            return

        chapters = data.get('chapters') or []
        if len(chapters) > 1:
            meta.has_embedded_cue = True
            meta.embedded_chapters = chapters

    def _detect_image(self, meta, fmt_data):
        IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.avif', '.tiff', '.tif', '.bmp', '.heic', '.heif'}
        IMAGE_FORMAT_NAMES = {'image2', 'jpeg_pipe', 'png_pipe', 'webp_pipe', 'bmp_pipe', 'tiff_pipe', 'avif'}
        ext = os.path.splitext(meta.filename)[1].lower()
        if ext in IMAGE_EXTENSIONS:
            return True
        format_name = str(fmt_data.get('format_name', '')).lower()
        if any(img_fmt in format_name for img_fmt in IMAGE_FORMAT_NAMES):
            return True
        if meta.video_tracks and not meta.audio_tracks and meta.duration <= 0:
            return True
        return False

    def _get_startup_info(self):
        if os.name == 'nt':
            info = subprocess.STARTUPINFO()
            info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            return info
        return None
