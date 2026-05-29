import builtins
import logging
import os
import re
import subprocess
import tempfile

from core.ffmpeg_helpers import (
    STREAMING_LOUDNORM_FILTER,
    VIDEO_CONTAINER_OUTPUTS,
    apply_audio_codec_args,
    apply_common_audio_options,
    get_ffmpeg_path,
    parse_ffmpeg_threads,
)
from core.formatting import get_effective_audio_codec


def _translate(msgid):
    translator = builtins.__dict__.get('_')
    if callable(translator):
        return translator(msgid)
    return msgid


def _translatef(msgid, **kwargs):
    return _translate(msgid).format(**kwargs)


class MergeTask:
    def __init__(self, input_list, target_format, settings, output_path):
        self.input_list = input_list  # list of MediaMetadata
        self.target_format = target_format
        self.settings = settings
        self.output_path = output_path
        self.ffmpeg_exe = get_ffmpeg_path()
        self.process = None
        self.stderr_lines = []
        self.total_duration = sum(
            float(getattr(m, 'duration', 0) or 0) for m in input_list
        )

    def stop(self):
        if self.process and self.process.poll() is None:
            try:
                self.process.kill()
                logging.info("Processus FFmpeg de fusion interrompu.")
            except Exception:
                logging.exception("Impossible d'interrompre FFmpeg (fusion).")

    def _apply_audio_codec_settings(self, cmd):
        if self.target_format in VIDEO_CONTAINER_OUTPUTS:
            codec_key = get_effective_audio_codec(self.target_format, self.settings)
        else:
            codec_key = self.target_format

        apply_common_audio_options(cmd, self.settings)
        apply_audio_codec_args(cmd, codec_key, self.settings)

        if (
            self.settings.get("audio_normalize_streaming", False)
            and self.settings.get("audio_mode", "convert") != "copy"
        ):
            cmd.extend(['-filter:a', STREAMING_LOUDNORM_FILTER])

    def run(self, progress_callback=None, stop_check_callback=None):
        for meta in self.input_list:
            if not os.path.isfile(meta.full_path):
                logging.error("Fichier d'entrée introuvable au moment de la fusion : %s", meta.full_path)
                raise FileNotFoundError(
                    _translatef(
                        "File not found (it may have been moved or deleted): {name}",
                        name=os.path.basename(meta.full_path),
                    )
                )

        list_fd, list_path = tempfile.mkstemp(suffix='.txt', prefix='amc_concat_')
        try:
            with os.fdopen(list_fd, 'w', encoding='utf-8') as f:
                for meta in self.input_list:
                    path = meta.full_path.replace('\\', '/').replace("'", "\\'")
                    f.write(f"file '{path}'\n")

            cmd = [self.ffmpeg_exe, '-y', '-f', 'concat', '-safe', '0', '-i', list_path]

            if self.target_format in VIDEO_CONTAINER_OUTPUTS:
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

            thread_count = parse_ffmpeg_threads(self.settings)
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
                    stripped = line.strip()
                    logging.debug("FFmpeg (merge): %s", stripped)
                    self.stderr_lines.append(stripped)
                    if len(self.stderr_lines) > 200:
                        self.stderr_lines.pop(0)

                    if progress_callback and self.total_duration > 0:
                        match = time_pattern.search(line)
                        if match:
                            try:
                                h, m, s = match.groups()
                                current_seconds = int(h) * 3600 + int(m) * 60 + float(s)
                                percent = int((current_seconds / self.total_duration) * 100)
                                progress_callback(min(max(percent, 0), 100))
                            except (ValueError, TypeError):
                                pass

            if self.process.returncode != 0:
                if stop_check_callback and stop_check_callback():
                    raise Exception("Stopped by user")
                logging.error("FFmpeg (fusion) a échoué avec le code %s", self.process.returncode)
                tail = "\n".join(self.stderr_lines[-50:])
                raise Exception(f"FFmpeg merge error (code {self.process.returncode}):\n{tail}")

            logging.info("Fusion terminée avec succès.")

        finally:
            try:
                os.unlink(list_path)
            except Exception:
                pass
