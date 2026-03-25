import os
import subprocess
import sys
import re
import logging # Ajout

from core.formatting import IMAGE_OUTPUT_FORMAT_KEYS, VIDEO_CONTAINER_FORMAT_KEYS, get_effective_audio_codec
from core.track_settings import get_effective_track_settings, get_kept_track_entries


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

STREAMING_LOUDNORM_FILTER = "loudnorm=I=-16:TP=-1:LRA=7"


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


def build_output_path(input_path, target_format, custom_output_dir=None):
    output_dir = resolve_output_dir(input_path, custom_output_dir=custom_output_dir)
    return os.path.join(output_dir, build_output_filename(input_path, target_format))


class ConversionTask:
    def __init__(self, input_data, target_format, settings, output_dir=None, output_path=None):
        self.meta = None
        if hasattr(input_data, 'full_path'):
            self.meta = input_data
            self.input_path = input_data.full_path
            self.duration = float(input_data.duration)
        else:
            self.input_path = str(input_data)
            self.duration = 0.0

        self.target_format = target_format
        self.settings = settings
        self.custom_output_dir = output_dir
        self.output_path = output_path
        self.ffmpeg_exe = self._get_ffmpeg_path()
        self.process = None
        self.last_command = []
        self.stderr_lines = []

        logging.debug(f"Tâche initialisée : {self.input_path} -> {self.target_format}") # LOG

    def _get_ffmpeg_path(self):
        if getattr(sys, 'frozen', False):
            base_path = sys._MEIPASS
        else:
            base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        
        ffmpeg_path = os.path.join(base_path, 'bin', 'ffmpeg.exe')
        if not os.path.exists(ffmpeg_path): 
            logging.warning("ffmpeg.exe non trouvé dans bin/, utilisation du PATH système")
            return "ffmpeg"
        return ffmpeg_path

    def _is_video_to_audio_conversion(self):
        return bool(
            self.meta
            and getattr(self.meta, 'has_video', False)
            and self.target_format not in ['mp4', 'mkv', 'mov']
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
            if selected_track is not None:
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

        if self.target_format in ['mp4', 'mkv', 'mov'] and mapped_container_tracks is not None:
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

    def _get_ffmpeg_threads_value(self):
        value = self.settings.get("ffmpeg_threads", "auto")
        if isinstance(value, str) and value.lower() == "auto":
            return None

        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return None

        return max(1, parsed)

    def _get_target_audio_codec(self):
        if self.target_format in VIDEO_CONTAINER_FORMAT_KEYS or self.target_format == "mov":
            return get_effective_audio_codec(self.target_format, self.settings)
        return self.target_format

    def _apply_common_audio_options(self, cmd):
        sample_rate = self.settings.get('audio_sample_rate', 'original')
        if sample_rate != 'original':
            cmd.extend(['-ar', sample_rate])

        channels = self.settings.get('audio_channels', 'original')
        if channels == '2':
            cmd.extend(['-ac', '2'])
        elif channels == '1':
            cmd.extend(['-ac', '1'])

    def _apply_encoded_audio_settings(self, cmd, mapped_container_tracks):
        codec_key = self._get_target_audio_codec()
        self._apply_common_audio_options(cmd)

        if codec_key == 'mp3':
            cmd.extend(['-c:a', 'libmp3lame'])
            if self.settings.get('rate_mode', 'cbr') == 'cbr':
                cmd.extend(['-b:a', self.settings.get('audio_bitrate', '192k')])
            else:
                cmd.extend(['-q:a', str(self.settings.get('audio_qscale', 0))])
        elif codec_key == 'aac':
            cmd.extend(['-c:a', 'aac'])
            if self.settings.get('rate_mode', 'cbr') == 'cbr':
                cmd.extend(['-b:a', self.settings.get('audio_bitrate', '192k')])
            else:
                cmd.extend(['-q:a', str(self.settings.get('audio_qscale', 3))])
        elif codec_key == 'opus':
            cmd.extend(['-c:a', 'libopus', '-b:a', self.settings.get('audio_bitrate', '192k')])
        elif codec_key == 'ogg':
            cmd.extend(['-c:a', 'libvorbis', '-q:a', str(self.settings.get('audio_qscale', 6))])
        elif codec_key == 'wma':
            cmd.extend(['-c:a', 'wmav2', '-b:a', self.settings.get('audio_bitrate', '128k')])
        elif codec_key == 'wav':
            depth = self.settings.get('audio_bit_depth', 'original')
            codec_map = {'16': 'pcm_s16le', '24': 'pcm_s24le', '32': 'pcm_f32le'}
            cmd.extend(['-c:a', codec_map.get(str(depth), 'pcm_s16le')])
        elif codec_key == 'flac':
            cmd.extend(['-c:a', 'flac', '-compression_level', str(self.settings.get('flac_compression', 5))])
            depth = self.settings.get('audio_bit_depth', 'original')
            if depth == '16':
                cmd.extend(['-sample_fmt', 's16'])
            elif depth == '24':
                cmd.extend(['-sample_fmt', 's32'])
        elif codec_key == 'alac':
            cmd.extend(['-c:a', 'alac'])
            depth = self.settings.get('audio_bit_depth', 'original')
            if depth == '16':
                cmd.extend(['-sample_fmt', 's16p'])
            elif depth == '24':
                cmd.extend(['-sample_fmt', 's32p'])

        self._apply_audio_normalization_filters(cmd, mapped_container_tracks)

    def _filter_subtitle_entries_for_container(self, subtitle_entries):
        if self.target_format not in ['mp4', 'mov']:
            return subtitle_entries

        compatible_entries = []
        for track_entry in subtitle_entries:
            codec_name = str(track_entry.get("codec_name", "")).lower()
            original_index = track_entry.get("original_index")

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

    def _apply_video_container_track_mapping(self, cmd):
        effective_track_settings = get_effective_track_settings(self.meta)
        kept_video_tracks = get_kept_track_entries(effective_track_settings, "video")
        if not kept_video_tracks:
            logging.error("Aucune piste vidéo conservée pour la sortie vidéo.")
            raise Exception("No video track selected")

        mapping_used = "personnalise" if getattr(self.meta, "track_settings", None) else "par defaut"
        logging.info("Utilisation du mapping vidéo explicite (%s).", mapping_used)

        mapped_entries = {
            "video": get_kept_track_entries(effective_track_settings, "video"),
            "audio": get_kept_track_entries(effective_track_settings, "audio"),
            "subtitle": self._filter_subtitle_entries_for_container(
                get_kept_track_entries(effective_track_settings, "subtitle")
            ),
        }

        for track_type in ("video", "audio", "subtitle"):
            kept_entries = mapped_entries[track_type]
            for output_index, track_entry in enumerate(kept_entries):
                cmd.extend(["-map", f"0:{track_entry['original_index']}"])
                self._apply_track_entry_metadata(cmd, track_type, output_index, track_entry)

        return mapped_entries

    def _build_image_command(self, output_path):
        cmd = [self.ffmpeg_exe, '-y', '-i', self.input_path]

        vf_filters = []
        resize = self.settings.get('image_resize', 'original')
        if resize and resize != 'original' and 'x' in resize:
            w, h = resize.split('x', 1)
            vf_filters.append(f"scale={w}:{h}:force_original_aspect_ratio=decrease")

        if vf_filters:
            cmd.extend(['-vf', ','.join(vf_filters)])

        fmt = self.target_format
        if fmt == 'jpeg':
            quality = int(self.settings.get('image_quality', 85))
            qv = max(2, 31 - int(quality * 29 / 100))
            cmd.extend(['-q:v', str(qv)])
        elif fmt == 'png':
            compression = int(self.settings.get('image_compression', 6))
            cmd.extend(['-compression_level', str(compression)])
        elif fmt == 'webp':
            if self.settings.get('image_lossless', False):
                cmd.extend(['-c:v', 'libwebp', '-lossless', '1'])
            else:
                quality = int(self.settings.get('image_quality', 80))
                cmd.extend(['-c:v', 'libwebp', '-quality', str(quality)])
        elif fmt == 'tiff':
            compression = str(self.settings.get('image_compression', 'lzw'))
            cmd.extend(['-compression_algo', compression])

        cmd.append('-an')

        thread_count = self._get_ffmpeg_threads_value()
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

        _, stderr_output = self.process.communicate(timeout=120)
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

    def run(self, progress_callback=None, stop_check_callback=None):
        output_path = self.output_path
        if not output_path:
            output_path = build_output_path(
                self.input_path,
                self.target_format,
                custom_output_dir=self.custom_output_dir,
            )

        output_dir = os.path.dirname(output_path) or os.getcwd()
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        if self.target_format in IMAGE_OUTPUT_FORMAT_KEYS:
            return self._run_image_conversion(output_path)

        # Construction Commande
        cmd = [self.ffmpeg_exe, '-y', '-i', self.input_path]
        mapped_container_tracks = None

        if self.target_format in ['mp4', 'mkv', 'mov'] and self.meta is not None:
            mapped_container_tracks = self._apply_video_container_track_mapping(cmd)
        else:
            logging.debug("Mode automatique (pas de mapping vidéo explicite)")

        if self._is_video_to_audio_conversion():
            selected_track, selection_source = self._resolve_audio_extract_track()
            if selected_track is not None:
                cmd.extend(['-map', f"0:{selected_track.index}"])
                self._apply_audio_track_metadata(cmd, selected_track)
                logging.info(
                    "Piste audio d'extraction utilisée (%s) : stream #%s",
                    selection_source,
                    selected_track.index,
                )
            else:
                logging.warning("Aucune piste audio explicite n'a pu être sélectionnée pour l'extraction.")

        # --- REGLAGES ---
        audio_mode = self.settings.get('audio_mode', 'convert')
        if audio_mode == 'copy':
            cmd.extend(['-c:a', 'copy'])
        else:
            self._apply_encoded_audio_settings(cmd, mapped_container_tracks)

        if self.target_format in ['mp4', 'mkv', 'mov']:
            video_mode = self.settings.get('video_mode', 'convert')
            if video_mode == 'copy':
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
            cmd.append('-vn')

        thread_count = self._get_ffmpeg_threads_value()
        if thread_count is not None:
            cmd.extend(['-threads', str(thread_count)])

        cmd.append(output_path)
        self.last_command = list(cmd)

        # LOG DE LA COMMANDE FINALE (Crucial !)
        logging.info(f"Commande FFmpeg: {' '.join(cmd)}")

        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        
        self.process = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.PIPE,
            universal_newlines=True, encoding='utf-8', errors='ignore',
            startupinfo=startupinfo, creationflags=subprocess.CREATE_NO_WINDOW
        )

        time_pattern = re.compile(r'time=(\d{2}):(\d{2}):(\d{2}\.\d+)')
        
        # Lecture ligne par ligne pour logger
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
                        except: pass

        if self.process.returncode != 0:
            if stop_check_callback and stop_check_callback():
                raise Exception("Stopped by user")
            logging.error(f"FFmpeg a échoué avec le code {self.process.returncode}")
            tail = "\n".join(self.stderr_lines[-50:])
            raise Exception(f"FFmpeg error (code {self.process.returncode}):\n{tail}")
        else:
            logging.info("Conversion terminée avec succès.")
