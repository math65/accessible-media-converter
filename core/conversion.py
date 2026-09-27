import os
import subprocess
import re
import json
import logging
import builtins

from core.ffmpeg_helpers import (
    COVER_ART_AUDIO_OUTPUTS,
    STREAMING_LOUDNORM_FILTER,
    VIDEO_CONTAINER_OUTPUTS,
    apply_audio_codec_args,
    apply_common_audio_options,
    apply_date_tag_compat,
    apply_id3v2_compat_args,
    apply_metadata_preservation,
    broadcast_input_args,
    detect_oversized_subtitle_streams,
    detect_uncopyable_streams,
    get_ffmpeg_path,
    get_ffprobe_path,
    parse_ffmpeg_threads,
    parse_oversized_subtitle_stream,
)
from core.formatting import IMAGE_OUTPUT_FORMAT_KEYS, get_effective_audio_codec
from core.probe import parse_stream_duration
from core.metadata_edit import (
    build_tag_metadata_args,
    cover_stream_args,
    get_metadata_overrides,
    overrides_are_effective,
)
from core.track_settings import (
    get_effective_track_settings,
    get_kept_track_entries,
    iter_media_tracks,
)


def _translate(msgid):
    translator = builtins.__dict__.get('_')
    if callable(translator):
        return translator(msgid)
    return msgid


def _translatef(msgid, **kwargs):
    return _translate(msgid).format(**kwargs)


MP4_TEXT_SUBTITLE_CODECS = frozenset(
    {
        "subrip",
        "srt",
        "ass",
        "ssa",
        "webvtt",
        "text",
        "mov_text",
    }
)


def get_output_extension(target_format):
    if target_format in ['alac', 'aac']:
        return 'm4a'
    if target_format == 'jpeg':
        return 'jpg'
    if target_format == 'tiff':
        return 'tif'
    return target_format


def build_output_filename(input_path, target_format):
    extension = get_output_extension(target_format)
    base_name = os.path.splitext(os.path.basename(input_path))[0]
    return f"{base_name}.{extension}"


def resolve_output_dir(input_path, custom_output_dir=None):
    if custom_output_dir and os.path.isdir(custom_output_dir):
        return custom_output_dir
    return os.path.dirname(input_path) or os.getcwd()


def build_output_path(input_path, target_format, custom_output_dir=None, relative_dir=""):
    output_dir = resolve_output_dir(input_path, custom_output_dir=custom_output_dir)
    # Recrée l'arborescence d'origine uniquement vers un dossier de sortie
    # personnalisé ; en mode « source » la structure est déjà préservée.
    if relative_dir and custom_output_dir and os.path.isdir(custom_output_dir):
        output_dir = os.path.join(output_dir, relative_dir)
    return os.path.join(output_dir, build_output_filename(input_path, target_format))


def _format_ffmpeg_time(ms):
    """Millisecondes → 'HH:MM:SS.mmm' accepté par ffmpeg (-ss/-t)."""
    total_seconds = max(0, ms) / 1000.0
    hours = int(total_seconds // 3600)
    minutes = int((total_seconds % 3600) // 60)
    seconds = total_seconds % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:06.3f}"


def sanitize_filename(name):
    """Retire les caractères interdits dans un nom de fichier Windows."""
    cleaned = re.sub(r'[\\/:*?"<>|]', '_', str(name)).strip(' .')
    return cleaned or "_"


def build_cue_track_output_path(image_path, album, number, total, title, target_format,
                                custom_output_dir=None, relative_dir=""):
    """Chemin d'une piste découpée : <dossier>/<album>/NN - Titre.ext."""
    base_dir = resolve_output_dir(image_path, custom_output_dir=custom_output_dir)
    if relative_dir and custom_output_dir and os.path.isdir(custom_output_dir):
        base_dir = os.path.join(base_dir, relative_dir)
    album_dir = os.path.join(base_dir, sanitize_filename(album) if album else "Album")
    width = max(2, len(str(total)))
    extension = get_output_extension(target_format)
    safe_title = sanitize_filename(title) if title else _translate("Track {number}").format(number=number)
    return os.path.join(album_dir, f"{number:0{width}d} - {safe_title}.{extension}")


class ConversionTask:
    def __init__(self, input_data, target_format, settings, output_dir=None, output_path=None,
                 clip=None, extra_tags=None, input_path_override=None):
        self.meta = None
        if hasattr(input_data, 'full_path'):
            self.meta = input_data
            self.input_path = input_data.full_path
            self.duration = float(input_data.duration)
        else:
            self.input_path = str(input_data)
            self.duration = 0.0

        # Mode « clip » (découpage cue) : on lit une tranche [start, end] d'une image
        # audio via input_path_override et on applique des tags explicites par piste.
        self.clip = clip
        self.extra_tags = extra_tags
        if input_path_override:
            self.input_path = input_path_override
        if clip:
            start_ms, end_ms = clip
            if end_ms is not None and end_ms > start_ms:
                self.duration = (end_ms - start_ms) / 1000.0

        self.target_format = target_format
        self.settings = settings
        self.custom_output_dir = output_dir
        self.output_path = output_path
        self.ffmpeg_exe = get_ffmpeg_path()
        self.ffprobe_exe = get_ffprobe_path()
        self.process = None
        self.last_command = []
        self.stderr_lines = []
        # Flux dont la copie a dû être abandonnée au profit d'un réencodage
        # (conteneur incapable de les accueillir tels quels) : lu par le
        # gestionnaire de lot pour le signaler dans la liste des fichiers.
        self.copy_fallback_kinds = set()
        # Sous-titres retirés parce que le muxeur MP4 n'a pas su écrire leurs
        # silences (voir ffmpeg_helpers) : lu par le gestionnaire de lot pour le
        # signaler dans la liste des fichiers.
        self.dropped_subtitle_tracks = set()
        # Flux de SORTIE refusés par le muxeur pendant l'exécution en cours.
        # Repéré à la volée : le tampon stderr ne garde que 200 lignes et le
        # message peut survenir loin de la fin sur un film long.
        self._oversized_subtitle_outputs = set()
        # Indices source mappés, dans l'ordre des -map (= ordre des flux de
        # sortie), pour retrouver la piste visée par un message du muxeur.
        self._mapped_source_indices = []
        self._last_mapped_entries = {}
        # Piste source retenue pour une extraction audio d'une vidéo.
        self._extract_source_index = None

        logging.debug("Tâche initialisée : %s -> %s", self.input_path, self.target_format)

    def _is_video_to_audio_conversion(self):
        return bool(
            self.meta
            and getattr(self.meta, 'has_video', False)
            and self.target_format not in VIDEO_CONTAINER_OUTPUTS
        )

    def _find_audio_track_by_index(self, original_index):
        if self.meta is None:
            return None

        if hasattr(self.meta, 'get_audio_track_by_index'):
            return self.meta.get_audio_track_by_index(original_index)

        for track in getattr(self.meta, 'audio_tracks', []):
            if getattr(track, 'index', None) == original_index:
                return track
        return None

    def _get_default_audio_track(self):
        if self.meta is None:
            return None

        if hasattr(self.meta, 'get_default_audio_track'):
            return self.meta.get_default_audio_track()

        audio_tracks = getattr(self.meta, 'audio_tracks', [])
        for track in audio_tracks:
            if hasattr(track, 'is_default') and track.is_default():
                return track
        if audio_tracks:
            return audio_tracks[0]
        return None

    def _resolve_audio_extract_track(self):
        selected_track_data = getattr(self.meta, 'audio_extract_track', None) if self.meta else None
        if isinstance(selected_track_data, dict):
            original_index = selected_track_data.get('original_index')
            selected_track = self._find_audio_track_by_index(original_index)
            if selected_track is not None and not (
                hasattr(selected_track, 'is_usable') and not selected_track.is_usable()
            ):
                return selected_track, "manual"

            logging.warning(
                "La piste audio d'extraction sélectionnée n'existe plus (stream #%s). Fallback automatique.",
                original_index,
            )

        default_track = self._get_default_audio_track()
        if default_track is None:
            return None, "missing"

        if hasattr(default_track, 'is_default') and default_track.is_default():
            return default_track, "default"
        return default_track, "first"

    def _apply_audio_track_metadata(self, cmd, track):
        if track.language and track.language != 'und':
            cmd.extend(["-metadata:s:a:0", f"language={track.language}"])
        if track.title:
            cmd.extend(["-metadata:s:a:0", f"title={track.title}"])

    def _apply_track_entry_metadata(self, cmd, track_type, output_index, track_entry):
        stream_letter = {"video": "v", "audio": "a", "subtitle": "s"}[track_type]
        language = track_entry.get("language")
        title = track_entry.get("title")

        if language and language != "und":
            cmd.extend([f"-metadata:s:{stream_letter}:{output_index}", f"language={language}"])
        if title:
            cmd.extend([f"-metadata:s:{stream_letter}:{output_index}", f"title={title}"])

        active_dispositions = [
            disposition_name
            for disposition_name, enabled in track_entry.get("dispositions", {}).items()
            if enabled
        ]
        disposition_value = "+".join(active_dispositions) if active_dispositions else "0"
        cmd.extend([f"-disposition:{stream_letter}:{output_index}", disposition_value])

    def _is_streaming_normalization_enabled(self):
        return bool(
            self.settings.get("audio_normalize_streaming", False)
            and self.settings.get("audio_mode", "convert") != "copy"
        )

    def _apply_audio_normalization_filters(self, cmd, mapped_container_tracks):
        if not self._is_streaming_normalization_enabled():
            return

        if self.target_format in VIDEO_CONTAINER_OUTPUTS and mapped_container_tracks is not None:
            audio_entries = mapped_container_tracks.get("audio", [])
            if not audio_entries:
                return

            for output_index, _track_entry in enumerate(audio_entries):
                cmd.extend([f"-filter:a:{output_index}", STREAMING_LOUDNORM_FILTER])

            logging.info(
                "Normalisation streaming appliquee sur %s piste(s) audio de sortie.",
                len(audio_entries),
            )
            return

        cmd.extend(["-filter:a", STREAMING_LOUDNORM_FILTER])
        logging.info("Normalisation streaming appliquee sur la sortie audio.")

    def _get_target_audio_codec(self):
        if self.target_format in VIDEO_CONTAINER_OUTPUTS:
            return get_effective_audio_codec(self.target_format, self.settings)
        if self.target_format == 'm4b':
            return 'aac'  # le M4B est un conteneur MP4 encodé en AAC
        return self.target_format

    def _apply_encoded_audio_settings(self, cmd, mapped_container_tracks):
        apply_common_audio_options(cmd, self.settings)
        apply_audio_codec_args(cmd, self._get_target_audio_codec(), self.settings)
        self._apply_audio_normalization_filters(cmd, mapped_container_tracks)

    def _filter_subtitle_entries_for_container(self, subtitle_entries, drop_indices=()):
        if self.target_format not in ['mp4', 'mov']:
            return subtitle_entries

        drop_indices = set(drop_indices or ())
        compatible_entries = []
        for track_entry in subtitle_entries:
            codec_name = str(track_entry.get("codec_name", "")).lower()
            original_index = track_entry.get("original_index")

            if original_index in drop_indices:
                # Silence trop long pour tx3g : la garder condamne l'audio.
                logging.warning(
                    "Sous-titre #%s retiré de %s : le conteneur ne sait pas écrire ses silences.",
                    original_index,
                    self.target_format.upper(),
                )
                continue

            if codec_name in MP4_TEXT_SUBTITLE_CODECS:
                if codec_name != "mov_text":
                    logging.info(
                        "Sous-titre #%s (%s) converti en mov_text pour %s.",
                        original_index,
                        codec_name or "unknown",
                        self.target_format.upper(),
                    )
                compatible_entries.append(track_entry)
                continue

            logging.warning(
                "Sous-titre #%s (%s) ignore pour %s car non compatible avec ce conteneur.",
                original_index,
                codec_name or "unknown",
                self.target_format.upper(),
            )

        return compatible_entries

    def _filter_entries_against_source(self, track_type, entries):
        """Écarte les pistes absentes ou illisibles dans CE fichier.

        Un réglage de pistes appliqué à plusieurs fichiers (« Gérer les pistes
        (N fichiers)… ») peut référencer un flux qui n'existe pas dans un fichier
        au sommaire plus court : FFmpeg rejetait alors toute la commande
        (« Stream map '' matches no streams » / « Failed to set value '0:4' for
        option 'map' »). Les flux dont FFmpeg n'a pas pu lire les paramètres sont
        écartés aussi : le muxeur MP4 refuse d'écrire l'en-tête sans eux
        (« sample rate not set »)."""
        source_tracks = {
            getattr(track, "index", None): track
            for track in iter_media_tracks(self.meta, track_type)
        }

        filtered_entries = []
        for entry in entries:
            original_index = entry.get("original_index")
            track = source_tracks.get(original_index)
            if track is None:
                logging.warning(
                    "Piste %s #%s absente de %s : ignorée du mapping.",
                    track_type, original_index, os.path.basename(self.input_path),
                )
                continue
            if hasattr(track, "is_usable") and not track.is_usable():
                logging.warning(
                    "Piste %s #%s illisible (paramètres de codec introuvables) dans %s : ignorée du mapping.",
                    track_type, original_index, os.path.basename(self.input_path),
                )
                continue
            filtered_entries.append(entry)
        return filtered_entries

    def _apply_video_container_track_mapping(self, cmd, drop_subtitles=()):
        effective_track_settings = get_effective_track_settings(self.meta)

        mapped_entries = {
            "video": self._filter_entries_against_source(
                "video", get_kept_track_entries(effective_track_settings, "video")
            ),
            "audio": self._filter_entries_against_source(
                "audio", get_kept_track_entries(effective_track_settings, "audio")
            ),
            "subtitle": self._filter_subtitle_entries_for_container(
                self._filter_entries_against_source(
                    "subtitle", get_kept_track_entries(effective_track_settings, "subtitle")
                ),
                drop_indices=drop_subtitles,
            ),
        }

        if not mapped_entries["video"]:
            logging.error("Aucune piste vidéo conservée pour la sortie vidéo (%s)", self.input_path)
            raise Exception(f"No video track selected for {os.path.basename(self.input_path)}")

        mapping_used = "personnalise" if getattr(self.meta, "track_settings", None) else "par defaut"
        logging.info("Utilisation du mapping vidéo explicite (%s).", mapping_used)

        self._last_mapped_entries = mapped_entries
        self._mapped_source_indices = []
        for track_type in ("video", "audio", "subtitle"):
            kept_entries = mapped_entries[track_type]
            for output_index, track_entry in enumerate(kept_entries):
                cmd.extend(["-map", f"0:{track_entry['original_index']}"])
                self._mapped_source_indices.append(track_entry['original_index'])
                self._apply_track_entry_metadata(cmd, track_type, output_index, track_entry)

        return mapped_entries

    def _build_image_command(self, output_path):
        cmd = [self.ffmpeg_exe, '-y', '-i', self.input_path]

        vf_filters = []
        resize = self.settings.get('image_resize', 'original')
        if resize and resize != 'original' and 'x' in resize:
            parts = resize.split('x', 1)
            try:
                w, h = int(parts[0]), int(parts[1])
                if w > 0 and h > 0:
                    vf_filters.append(f"scale={w}:{h}:force_original_aspect_ratio=decrease")
            except (ValueError, IndexError):
                logging.warning("Valeur de resize invalide ignorée: %s", resize)

        if vf_filters:
            cmd.extend(['-vf', ','.join(vf_filters)])

        fmt = self.target_format
        if fmt == 'jpeg':
            quality = max(1, min(100, int(self.settings.get('image_quality', 85))))
            qv = max(2, min(31, 31 - int((quality - 1) * 29 / 99)))
            cmd.extend(['-q:v', str(qv)])
        elif fmt == 'png':
            compression = max(0, min(9, int(self.settings.get('image_compression', 6))))
            cmd.extend(['-compression_level', str(compression)])
        elif fmt == 'webp':
            if self.settings.get('image_lossless', False):
                cmd.extend(['-c:v', 'libwebp', '-lossless', '1'])
            else:
                quality = max(0, min(100, int(self.settings.get('image_quality', 80))))
                cmd.extend(['-c:v', 'libwebp', '-quality', str(quality)])
        elif fmt == 'tiff':
            # Le jeton « non compressé » de l'encodeur TIFF FFmpeg est 'raw', pas
            # 'none' (qui est rejeté au parsing de -compression_algo).
            valid_tiff = ('lzw', 'deflate', 'packbits', 'raw')
            compression = str(self.settings.get('image_compression', 'lzw')).lower()
            if compression == 'none':
                compression = 'raw'
            if compression not in valid_tiff:
                compression = 'lzw'
            cmd.extend(['-compression_algo', compression])

        cmd.append('-an')
        # Une entrée peut contenir plusieurs images (WebP animé, GIF, HEIC avec
        # sa miniature) : la sortie image est un fichier unique, donc on n'en
        # encode qu'une. Sans ça le muxeur image2 échoue en cours de route
        # (« Error muxing a packet ») et la conversion est perdue.
        cmd.extend(['-frames:v', '1'])

        thread_count = parse_ffmpeg_threads(self.settings)
        if thread_count is not None:
            cmd.extend(['-threads', str(thread_count)])

        cmd.append(output_path)
        return cmd

    def _run_image_conversion(self, output_path):
        cmd = self._build_image_command(output_path)
        self.last_command = list(cmd)
        logging.info(f"Commande FFmpeg (image): {' '.join(cmd)}")

        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        self.process = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.PIPE,
            universal_newlines=True, encoding='utf-8', errors='ignore',
            startupinfo=startupinfo, creationflags=subprocess.CREATE_NO_WINDOW
        )

        try:
            _, stderr_output = self.process.communicate(timeout=120)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.communicate()
            raise Exception("FFmpeg image conversion timed out after 120 seconds")

        if stderr_output:
            for line in stderr_output.strip().splitlines()[-50:]:
                self.stderr_lines.append(line.strip())

        if self.process.returncode != 0:
            logging.error(f"FFmpeg image a échoué avec le code {self.process.returncode}")
            tail = "\n".join(self.stderr_lines[-50:])
            raise Exception(f"FFmpeg error (code {self.process.returncode}):\n{tail}")

        logging.info("Conversion image terminée avec succès.")

    def stop(self):
        if self.process and self.process.poll() is None:
            try:
                self.process.kill()
                logging.info("Processus FFmpeg interrompu pour: %s", self.input_path)
            except Exception:
                logging.exception("Impossible d'interrompre FFmpeg pour: %s", self.input_path)

    def _probe_duration(self, path):
        """Renvoie la durée (secondes) d'un fichier via ffprobe, ou None si illisible."""
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        try:
            result = subprocess.run(
                [
                    self.ffprobe_exe, '-v', 'error',
                    '-show_entries', 'format=duration',
                    '-of', 'default=noprint_wrappers=1:nokey=1', path,
                ],
                capture_output=True, text=True, timeout=30,
                startupinfo=startupinfo, creationflags=subprocess.CREATE_NO_WINDOW,
            )
            return float(result.stdout.strip())
        except (ValueError, subprocess.SubprocessError, OSError):
            return None

    def _probe_stream_durations(self, path):
        """Flux du fichier dans l'ordre de sortie : [(type, durée, pochette), ...].

        La durée vaut None quand le format ne la porte pas (Matroska sans tag).
        """
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        streams = []
        try:
            result = subprocess.run(
                [
                    self.ffprobe_exe, '-v', 'error',
                    '-show_entries',
                    'stream=codec_type,duration,duration_ts,time_base'
                    ':stream_tags=DURATION:stream_disposition=attached_pic',
                    '-print_format', 'json', path,
                ],
                capture_output=True, text=True, timeout=30,
                startupinfo=startupinfo, creationflags=subprocess.CREATE_NO_WINDOW,
            )
            for stream in (json.loads(result.stdout or '{}').get('streams') or []):
                disposition = stream.get('disposition') or {}
                streams.append((
                    stream.get('codec_type'),
                    parse_stream_duration(stream),
                    bool(disposition.get('attached_pic', 0)),
                ))
        except (ValueError, subprocess.SubprocessError, OSError):
            return []
        return streams

    def _source_track_duration(self, original_index, kinds=('video', 'audio', 'subtitle')):
        """Durée connue de la piste source d'indice donné, sinon None."""
        for kind in kinds:
            for track in getattr(self.meta, f"{kind}_tracks", None) or []:
                if getattr(track, 'index', None) == original_index:
                    return getattr(track, 'duration', None)
        return None

    def _expected_container_duration(self):
        """Durée attendue de la sortie entière.

        Celle du conteneur source, sauf quand on sait quelles pistes partent
        dans la sortie : extraire une piste de 5 s d'une vidéo de 60 s donne
        légitimement 5 s. On prend la plus longue des pistes retenues dont la
        durée est connue ; sans aucune mesure, la durée source.
        """
        if self.clip or self.meta is None:
            return self.duration
        if self._extract_source_index is not None:
            indices = [self._extract_source_index]
        else:
            indices = list(self._mapped_source_indices)
        known = [
            duration for duration in (
                self._source_track_duration(i, kinds=('video', 'audio')) for i in indices
            )
            if duration is not None
        ]
        return max(known) if known else self.duration

    def _expected_duration_for_output(self, position, kind):
        """Durée attendue pour le flux de sortie n° ``position``.

        On se réfère à la piste SOURCE qui l'a produit quand sa durée est
        connue : une source dont une piste audio ne fait que 17 s produit
        légitimement 17 s de son, ce n'est pas la conversion qui a échoué
        (l'utilisateur a déjà été prévenu au chargement). Comparer chaque flux
        à la plus LONGUE piste du même type faisait échouer toute conversion
        d'un fichier gardant une piste courte à côté d'une complète.
        Sans mesure côté source — ou sur un extrait, où les durées de pistes ne
        s'appliquent plus — on retombe sur la durée de référence.
        """
        if self.clip or self.meta is None:
            return self.duration

        source_index = None
        if self._mapped_source_indices:
            # Mapping explicite (sortie vidéo) : l'ordre des -map est celui des
            # flux de sortie.
            if position < len(self._mapped_source_indices):
                source_index = self._mapped_source_indices[position]
        elif kind == 'audio' and self._extract_source_index is not None:
            # Extraction audio d'une vidéo : une seule piste choisie.
            source_index = self._extract_source_index

        if source_index is not None:
            duration = self._source_track_duration(source_index)
            return duration if duration is not None else self.duration

        # Sélection automatique de FFmpeg : on ne sait pas quelle piste il a
        # retenue, on prend la plus longue (hypothèse la plus prudente).
        tracks = getattr(self.meta, f"{kind}_tracks", None) or []
        known = [
            track.duration for track in tracks
            if getattr(track, 'duration', None) is not None
        ]
        if not known:
            return self.duration
        return max(known)

    def _output_looks_truncated(self, output_path):
        """Heuristique conservatrice : une conversion saine conserve la durée.

        Deux contrôles. Celui du CONTENEUR attrape les sorties globalement
        amputées. Celui par FLUX comble le trou qu'il laissait : la durée d'un
        conteneur est celle de son flux le plus long, donc une sortie dont la
        vidéo est complète mais dont l'audio meurt en route affichait 100 % et
        passait pour une réussite (cas terrain d'août 2026).

        On ne signale que les amputations franches (moins de la moitié de
        l'attendu) pour éviter tout faux positif — un générique muet, une piste
        d'audiodescription plus courte que le film sont légitimes.
        """
        if not self.duration or self.duration <= 5:
            return False
        if not os.path.isfile(output_path):
            return True

        out_duration = self._probe_duration(output_path)
        if out_duration is None:
            return True
        if out_duration < self._expected_container_duration() * 0.5:
            return True

        for position, (kind, value, is_cover) in enumerate(self._probe_stream_durations(output_path)):
            if kind not in ('audio', 'video') or is_cover or value is None:
                continue
            expected = self._expected_duration_for_output(position, kind)
            if not expected or expected <= 5:
                continue
            if value < expected * 0.5:
                logging.error(
                    "Flux %s n°%s tronqué dans la sortie : %.1f s pour %.1f s attendues (%s).",
                    kind, position, value, expected, os.path.basename(output_path),
                )
                return True
        return False

    def run(self, progress_callback=None, stop_check_callback=None, drop_cover=False,
            force_reencode=None, drop_subtitles=None):
        drop_subtitles = set(drop_subtitles or ())
        # Chaque tentative repart avec ses propres constats de muxage.
        self._oversized_subtitle_outputs = set()
        if not os.path.isfile(self.input_path):
            logging.error("Fichier d'entrée introuvable au moment de la conversion : %s", self.input_path)
            raise FileNotFoundError(
                _translatef(
                    "File not found (it may have been moved or deleted): {name}",
                    name=os.path.basename(self.input_path),
                )
            )

        output_path = self.output_path
        if not output_path:
            output_path = build_output_path(
                self.input_path,
                self.target_format,
                custom_output_dir=self.custom_output_dir,
            )

        output_dir = os.path.dirname(output_path) or os.getcwd()
        # exist_ok : plusieurs pistes d'un même cue créent le sous-dossier album en
        # parallèle (sinon WinError 183 sur le perdant de la course).
        os.makedirs(output_dir, exist_ok=True)

        if self.target_format in IMAGE_OUTPUT_FORMAT_KEYS:
            return self._run_image_conversion(output_path)

        overrides = get_metadata_overrides(self.meta) if self.meta is not None else {}
        override_tags = overrides.get('tags', {}) if overrides else {}
        cover = overrides.get('cover', {}) if overrides else {}
        cover_action = cover.get('action', 'keep')

        audio_output = self.target_format not in VIDEO_CONTAINER_OUTPUTS
        cover_capable = self.target_format in COVER_ART_AUDIO_OUTPUTS
        cover_replace = cover_action == 'replace' and audio_output and cover_capable
        cover_path = cover.get('path') if cover_replace else None

        cmd = [self.ffmpeg_exe, '-y']
        # Captures TV (.ts/.mpg/.vob…) : PTS manquants, DTS non-monotones et
        # paramètres de flux découverts tardivement → genpts + analyse élargie.
        cmd.extend(broadcast_input_args(self.input_path))
        clip_start_ms = clip_end_ms = None
        if self.clip:
            clip_start_ms, clip_end_ms = self.clip
            # -ss avant -i : seek d'entrée rapide et précis en réencodage.
            cmd.extend(['-ss', _format_ffmpeg_time(clip_start_ms)])
        cmd.extend(['-i', self.input_path])
        if cover_replace and cover_path:
            cmd.extend(['-i', cover_path])  # 2e entrée = nouvelle pochette (index 1)
        if clip_start_ms is not None and clip_end_ms is not None and clip_end_ms > clip_start_ms:
            # -t après toutes les entrées → s'applique à la sortie (durée de la piste).
            cmd.extend(['-t', _format_ffmpeg_time(clip_end_ms - clip_start_ms)])
        mapped_container_tracks = None

        if self.target_format in VIDEO_CONTAINER_OUTPUTS and self.meta is not None:
            mapped_container_tracks = self._apply_video_container_track_mapping(
                cmd, drop_subtitles=drop_subtitles
            )
        else:
            logging.debug("Mode automatique (pas de mapping vidéo explicite)")

        if self._is_video_to_audio_conversion():
            selected_track, selection_source = self._resolve_audio_extract_track()
            if selected_track is not None:
                self._extract_source_index = selected_track.index
                cmd.extend(['-map', f"0:{selected_track.index}"])
                self._apply_audio_track_metadata(cmd, selected_track)
                logging.info(
                    "Piste audio d'extraction utilisée (%s) : stream #%s",
                    selection_source,
                    selected_track.index,
                )
            else:
                logging.warning("Aucune piste audio explicite n'a pu être sélectionnée pour l'extraction.")

        if cover_replace and cover_path:
            # Une fois la pochette mappée, la sélection auto est désactivée :
            # mapper explicitement l'audio (sauf si déjà fait pour l'extraction).
            if not self._is_video_to_audio_conversion():
                cmd.extend(['-map', '0:a'])
            cmd.extend(['-map', '1:0'])

        if self.clip:
            # Découpage cue : tags explicites par piste, sans recopie des métadonnées
            # de l'image (sinon le titre de l'album contaminerait chaque piste).
            preserve_metadata = False
            if self.extra_tags:
                cmd.extend(build_tag_metadata_args(self.extra_tags))
        else:
            preserve_metadata = apply_metadata_preservation(cmd, self.settings)

            if overrides_are_effective(overrides):
                # L'édition conserve les tags non modifiés, puis surcharge les champs édités.
                if not preserve_metadata:
                    cmd.extend(['-map_metadata', '0', '-map_chapters', '0'])
                    preserve_metadata = True
                cmd.extend(build_tag_metadata_args(override_tags))

            if self.target_format == 'm4b' and not preserve_metadata:
                # Le M4B est un livre audio : on conserve toujours les chapitres (et
                # tags) de la source lors d'une conversion d'un seul fichier.
                cmd.extend(['-map_metadata', '0', '-map_chapters', '0'])
                preserve_metadata = True

            if preserve_metadata and not override_tags.get('date') and self.meta is not None:
                # La date heritee de la source peut etre un horodatage complet (fichiers
                # iTunes) que Windows n'affiche pas : on la ramene a une forme lisible.
                # Apres les tags edites il ecraserait le choix de l'utilisateur, d'ou la
                # garde sur override_tags.
                apply_date_tag_compat(cmd, self.meta, self.target_format)

        # force_reencode : flux que le conteneur a refusés en copie lors d'une
        # première tentative (voir la reprise en fin de run).
        force_reencode = set(force_reencode or ())
        copy_kinds = set()

        audio_mode = self.settings.get('audio_mode', 'convert')
        if audio_mode == 'copy' and 'audio' not in force_reencode:
            copy_kinds.add('audio')
            cmd.extend(['-c:a', 'copy'])
        else:
            self._apply_encoded_audio_settings(cmd, mapped_container_tracks)

        used_cover_copy = False
        if self.target_format in VIDEO_CONTAINER_OUTPUTS:
            video_mode = self.settings.get('video_mode', 'convert')
            if video_mode == 'copy' and 'video' not in force_reencode:
                copy_kinds.add('video')
                cmd.extend(['-c:v', 'copy'])
            else:
                crf = str(self.settings.get('video_crf', 23))
                encoder_preset = str(self.settings.get('video_encoder_preset', 'medium') or 'medium')
                pixel_format = str(self.settings.get('video_pixel_format', 'yuv420p') or 'yuv420p')
                cmd.extend(['-c:v', 'libx264', '-crf', crf, '-preset', encoder_preset, '-pix_fmt', pixel_format])

                if pixel_format == 'yuv420p':
                    video_profile = str(self.settings.get('video_profile', 'high') or 'high')
                    cmd.extend(['-profile:v', video_profile])
                else:
                    logging.info(
                        "Profil H.264 ignoré pour le pixel format %s afin d'éviter une combinaison invalide.",
                        pixel_format,
                    )

            if mapped_container_tracks and mapped_container_tracks.get("subtitle"):
                if self.target_format in ['mp4', 'mov']:
                    cmd.extend(['-c:s', 'mov_text'])
                elif self.target_format == 'mkv':
                    cmd.extend(['-c:s', 'copy'])
        else:
            if cover_replace and cover_path:
                # Nouvelle pochette (éditeur de métadonnées) : copier le flux image
                # ajouté en 2e entrée et le marquer attached_pic.
                cmd.extend(['-c:v', 'copy'])
                cmd.extend(cover_stream_args(0))
            elif (
                preserve_metadata
                and self.target_format in COVER_ART_AUDIO_OUTPUTS
                and not self._is_video_to_audio_conversion()
                and not drop_cover
            ):
                # Source sans vraie piste vidéo : tenter de conserver la pochette
                # attached_pic d'origine (sélection de flux par défaut). ATTENTION :
                # certaines pochettes (podcasts Radio France) sont un flux mjpeg à
                # paquet unique SANS timestamp (PTS=N/A) et de durée = celle du
                # fichier ; FFmpeg ne sait pas les ordonner dans le mux et tronque
                # tout l'audio (sortie ~20 Ko en code 0). On détecte ce cas après coup
                # (durée de sortie << durée source) et on relance sans pochette : voir
                # la validation en fin de run() (drop_cover=True).
                cmd.extend(['-c:v', 'copy'])
                used_cover_copy = True
            else:
                # Sortie audio sans pochette à conserver : on supprime le flux vidéo.
                # Les tags et chapitres restent préservés via -map_metadata /
                # -map_chapters appliqués plus haut.
                cmd.append('-vn')

        thread_count = parse_ffmpeg_threads(self.settings)
        if thread_count is not None:
            cmd.extend(['-threads', str(thread_count)])

        if self.target_format == 'm4b':
            # Le muxer ipod gère .m4b (sinon FFmpeg ne déduit pas le conteneur).
            cmd.extend(['-f', 'ipod'])

        apply_id3v2_compat_args(cmd, output_path)

        cmd.append(output_path)
        self.last_command = list(cmd)

        logging.info("Commande FFmpeg: %s", ' '.join(cmd))

        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        
        self.process = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.PIPE,
            universal_newlines=True, encoding='utf-8', errors='ignore',
            startupinfo=startupinfo, creationflags=subprocess.CREATE_NO_WINDOW
        )

        time_pattern = re.compile(r'time=(\d{2}):(\d{2}):(\d{2}\.\d+)')

        try:
            self._read_ffmpeg_progress(time_pattern, progress_callback, stop_check_callback)
        finally:
            # Sans ça, les tubes du sous-processus restent ouverts jusqu'au
            # ramasse-miettes : sur un lot de plusieurs dizaines de fichiers on
            # accumule des descripteurs pour rien.
            self._close_process_streams()

        if self.process.returncode != 0:
            if stop_check_callback and stop_check_callback():
                raise Exception("Stopped by user")

            # Copie impossible dans ce conteneur (un AVI DivX/msmpeg4v3 vers du MP4,
            # par exemple) : le muxeur n'a pas de tag pour ce codec, refuse d'écrire
            # l'en-tête, et TOUT le fichier échoue. Plutôt que de rendre l'erreur à
            # l'utilisateur, on refait la conversion en réencodant le ou les flux
            # fautifs — c'est bien le format qu'il a demandé, la copie n'était qu'un
            # raccourci. copy_kinds ne contient que les flux encore en copie, donc
            # la reprise converge : au pire deux passes (vidéo puis audio).
            retry_kinds = detect_uncopyable_streams(
                self.stderr_lines, [self.meta], copy_kinds
            )
            if retry_kinds:
                logging.warning(
                    "Copie impossible vers %s pour %s (%s) : nouvelle tentative en réencodage.",
                    self.target_format,
                    os.path.basename(self.input_path),
                    ", ".join(sorted(retry_kinds)),
                )
                self.copy_fallback_kinds = set(force_reencode) | retry_kinds
                # La sortie de la tentative avortée n'a plus d'intérêt : la vider
                # garde le rapport d'erreur (et la détection ci-dessus) sur la
                # seule commande réellement exécutée en dernier.
                self.stderr_lines = []
                return self.run(
                    progress_callback,
                    stop_check_callback,
                    drop_cover=drop_cover,
                    force_reencode=self.copy_fallback_kinds,
                    drop_subtitles=drop_subtitles,
                )

            logging.error(f"FFmpeg a échoué avec le code {self.process.returncode}")
            tail = "\n".join(self.stderr_lines[-50:])
            raise Exception(f"FFmpeg error (code {self.process.returncode}):\n{tail}")
        else:
            # Filet anti-échec-silencieux : FFmpeg renvoie parfois le code 0 tout en
            # produisant une sortie tronquée (pochette attached_pic ingérable, source
            # corrompue, etc.). On compare la durée produite à la durée source.
            if self._output_looks_truncated(output_path):
                if used_cover_copy and not drop_cover:
                    logging.warning(
                        "Sortie tronquée avec copie de pochette (%s) : nouvelle tentative sans pochette (-vn).",
                        os.path.basename(output_path),
                    )
                    return self.run(
                        progress_callback,
                        stop_check_callback,
                        drop_cover=True,
                        force_reencode=force_reencode,
                        drop_subtitles=drop_subtitles,
                    )
                culprits = self._subtitle_streams_to_drop(drop_subtitles)
                if culprits:
                    logging.warning(
                        "Sortie tronquée (%s) : nouvelle tentative sans le(s) sous-titre(s) %s, "
                        "dont le conteneur ne sait pas écrire les silences.",
                        os.path.basename(output_path),
                        ", ".join(str(index) for index in sorted(culprits)),
                    )
                    self.dropped_subtitle_tracks |= culprits
                    self.stderr_lines = []
                    return self.run(
                        progress_callback,
                        stop_check_callback,
                        drop_cover=drop_cover,
                        force_reencode=force_reencode,
                        drop_subtitles=drop_subtitles | culprits,
                    )
                tail = "\n".join(self.stderr_lines[-50:])
                logging.error("Fichier de sortie anormalement court : %s", output_path)
                raise Exception(
                    _translate(
                        "The converted file is unexpectedly short — the conversion likely failed."
                    )
                    + (f"\n{tail}" if tail else "")
                )
            logging.info("Conversion terminée avec succès.")

    def _subtitle_streams_to_drop(self, already_dropped):
        """Sous-titres à retirer pour récupérer l'audio de la sortie.

        Passé un certain silence entre deux répliques, le muxeur MP4 refuse
        l'échantillon vide qui devrait le combler ET cesse d'écrire l'audio,
        tout en terminant en code 0 (mécanisme détaillé dans ffmpeg_helpers).
        On ne retire que la piste que FFmpeg a lui-même nommée, jamais sur une
        supposition de durée : sans message, l'échec remonte tel quel.
        """
        if self.target_format not in ('mp4', 'mov'):
            return set()
        flagged = set(self._oversized_subtitle_outputs)
        flagged |= detect_oversized_subtitle_streams(self.stderr_lines)
        if not flagged:
            return set()

        subtitle_indices = {
            entry.get('original_index')
            for entry in (self._last_mapped_entries or {}).get('subtitle', ())
        }
        culprits = set()
        for output_index in flagged:
            if 0 <= output_index < len(self._mapped_source_indices):
                culprits.add(self._mapped_source_indices[output_index])
        culprits &= subtitle_indices
        return culprits - set(already_dropped or ())

    def _close_process_streams(self):
        for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
            if stream is None:
                continue
            try:
                stream.close()
            except OSError:
                pass

    def _read_ffmpeg_progress(self, time_pattern, progress_callback, stop_check_callback):
        while True:
            if stop_check_callback and stop_check_callback():
                logging.info("Interruption demandée par l'utilisateur.")
                self.process.kill()
                raise Exception("Stopped by user")

            line = self.process.stderr.readline()
            if not line and self.process.poll() is not None: break
            
            if line:
                stripped = line.strip()
                logging.debug(f"FFmpeg output: {stripped}")
                self.stderr_lines.append(stripped)
                flagged = parse_oversized_subtitle_stream(stripped)
                if flagged is not None:
                    self._oversized_subtitle_outputs.add(flagged)
                if len(self.stderr_lines) > 200:
                    self.stderr_lines.pop(0)

                if progress_callback:
                    match = time_pattern.search(line)
                    if match and self.duration > 0:
                        try:
                            h, m, s = match.groups()
                            current_seconds = int(h) * 3600 + int(m) * 60 + float(s)
                            percent = int((current_seconds / self.duration) * 100)
                            progress_callback(min(max(percent, 0), 100))
                        except (ValueError, TypeError):
                            pass
