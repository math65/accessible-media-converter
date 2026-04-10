import logging
import os
import re
import subprocess
import sys
import tempfile

from core.conversion import STREAMING_LOUDNORM_FILTER
from core.formatting import VIDEO_CONTAINER_FORMAT_KEYS, get_effective_audio_codec


class MergeTask:
    def __init__(self, input_list, target_format, settings, output_path):
        self.input_list = input_list  # list of MediaMetadata
        self.target_format = target_format
        self.settings = settings
        self.output_path = output_path
        self.ffmpeg_exe = self._get_ffmpeg_path()
        self.process = None
        self.total_duration = sum(
            float(getattr(m, 'duration', 0) or 0) for m in input_list
        )

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

    def stop(self):
        if self.process and self.process.poll() is None:
            try:
                self.process.kill()
                logging.info("Processus FFmpeg de fusion interrompu.")
            except Exception:
                logging.exception("Impossible d'interrompre FFmpeg (fusion).")

    def _get_ffmpeg_threads_value(self):
        value = self.settings.get("ffmpeg_threads", "auto")
        if isinstance(value, str) and value.lower() == "auto":
            return None
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return None
        return max(1, parsed)

    def _apply_common_audio_options(self, cmd):
        sample_rate = self.settings.get('audio_sample_rate', 'original')
        if sample_rate != 'original':
            cmd.extend(['-ar', sample_rate])
        channels = self.settings.get('audio_channels', 'original')
        if channels == '2':
            cmd.extend(['-ac', '2'])
        elif channels == '1':
            cmd.extend(['-ac', '1'])

    def _apply_audio_codec_settings(self, cmd):
        if self.target_format in VIDEO_CONTAINER_FORMAT_KEYS:
            codec_key = get_effective_audio_codec(self.target_format, self.settings)
        else:
            codec_key = self.target_format

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

        if (
            self.settings.get("audio_normalize_streaming", False)
            and self.settings.get("audio_mode", "convert") != "copy"
        ):
            cmd.extend(['-filter:a', STREAMING_LOUDNORM_FILTER])

    def run(self, progress_callback=None, stop_check_callback=None):
        list_fd, list_path = tempfile.mkstemp(suffix='.txt', prefix='amc_concat_')
        try:
            with os.fdopen(list_fd, 'w', encoding='utf-8') as f:
                for meta in self.input_list:
                    path = meta.full_path.replace('\\', '/').replace("'", "\\'")
                    f.write(f"file '{path}'\n")

            cmd = [self.ffmpeg_exe, '-y', '-f', 'concat', '-safe', '0', '-i', list_path]

            if self.target_format in VIDEO_CONTAINER_FORMAT_KEYS:
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
                audio_mode = self.settings.get('audio_mode', 'convert')
                if audio_mode == 'copy':
                    cmd.extend(['-c:a', 'copy'])
                else:
                    self._apply_audio_codec_settings(cmd)
            else:
                audio_mode = self.settings.get('audio_mode', 'convert')
                if audio_mode == 'copy':
                    cmd.extend(['-c:a', 'copy'])
                else:
                    self._apply_audio_codec_settings(cmd)
                cmd.append('-vn')

            thread_count = self._get_ffmpeg_threads_value()
            if thread_count is not None:
                cmd.extend(['-threads', str(thread_count)])

            cmd.append(self.output_path)

            logging.info("Commande FFmpeg (fusion): %s", ' '.join(cmd))

            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.PIPE,
                universal_newlines=True,
                encoding='utf-8',
                errors='ignore',
                startupinfo=startupinfo,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )

            time_pattern = re.compile(r'time=(\d{2}):(\d{2}):(\d{2}\.\d+)')

            while True:
                if stop_check_callback and stop_check_callback():
                    logging.info("Fusion : interruption demandée par l'utilisateur.")
                    self.process.kill()
                    raise Exception("Stopped by user")

                line = self.process.stderr.readline()
                if not line and self.process.poll() is not None:
                    break

                if line:
                    logging.debug("FFmpeg (merge): %s", line.strip())
                    if progress_callback and self.total_duration > 0:
                        match = time_pattern.search(line)
                        if match:
                            try:
                                h, m, s = match.groups()
                                current_seconds = int(h) * 3600 + int(m) * 60 + float(s)
                                percent = int((current_seconds / self.total_duration) * 100)
                                progress_callback(min(max(percent, 0), 100))
                            except Exception:
                                pass

            if self.process.returncode != 0:
                if stop_check_callback and stop_check_callback():
                    raise Exception("Stopped by user")
                logging.error("FFmpeg (fusion) a échoué avec le code %s", self.process.returncode)
                raise Exception("FFmpeg merge error")

            logging.info("Fusion terminée avec succès.")

        finally:
            try:
                os.unlink(list_path)
            except Exception:
                pass
