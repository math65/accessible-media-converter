"""Re-tag an existing media file in place, without re-encoding (`-c copy`).

Writes to a temp file in the same directory and atomically replaces the
original on success. The original is left untouched if anything fails.
"""

import logging
import os
import subprocess
import tempfile

from core.ffmpeg_helpers import apply_id3v2_compat_args, get_ffmpeg_path
from core.metadata_edit import (
    build_tag_metadata_args,
    cover_stream_args,
    overrides_are_effective,
    source_supports_cover,
)


class MetadataRetagError(Exception):
    pass


class MetadataRetagTask:
    def __init__(self, meta, overrides):
        self.meta = meta
        self.input_path = meta.full_path
        self.overrides = overrides or {}
        self.ffmpeg_exe = get_ffmpeg_path()
        self.last_command = []
        self.stderr_lines = []

    def _kept_video_stream_count(self):
        """Flux vidéo de la source qui restent dans la sortie (hors pochettes)."""
        total = getattr(self.meta, 'video_stream_count', 0) or 0
        covers = len(getattr(self.meta, 'cover_stream_indices', None) or [])
        return max(0, total - covers)

    def _build_command(self, temp_path):
        tags = self.overrides.get('tags', {})
        cover = self.overrides.get('cover', {})
        action = cover.get('action', 'keep')
        cover_path = cover.get('path') if action == 'replace' else None
        can_cover = source_supports_cover(getattr(self.meta, 'source_format_name', ''))

        cmd = [self.ffmpeg_exe, '-y', '-i', self.input_path]

        # Retirer l'ancienne pochette PAR SON INDEX, jamais « tous les flux
        # vidéo » (-map -0:v) : sur un film, c'est la piste vidéo elle-même qui
        # partait, et le fichier d'origine était remplacé par une version sans image.
        drop_covers = []
        for index in getattr(self.meta, 'cover_stream_indices', None) or []:
            drop_covers.extend(['-map', f'-0:{index}'])

        if action == 'replace' and cover_path and can_cover:
            cmd.extend(['-i', cover_path])
            # Garder tous les flux source sauf l'ancienne pochette, ajouter la nouvelle.
            cmd.extend(['-map', '0', *drop_covers, '-map', '1:0', '-c', 'copy'])
            # La nouvelle pochette suit tous les flux vidéo conservés.
            cmd.extend(cover_stream_args(self._kept_video_stream_count()))
        elif action == 'remove' and can_cover:
            cmd.extend(['-map', '0', *drop_covers, '-c', 'copy'])
        else:
            cmd.extend(['-map', '0', '-c', 'copy'])

        cmd.extend(['-map_metadata', '0', '-map_chapters', '0'])
        cmd.extend(build_tag_metadata_args(tags))
        apply_id3v2_compat_args(cmd, temp_path)
        cmd.append(temp_path)
        return cmd

    def run(self):
        if not os.path.isfile(self.input_path):
            raise MetadataRetagError(f"File not found: {self.input_path}")
        if not overrides_are_effective(self.overrides):
            return  # rien à appliquer

        directory = os.path.dirname(self.input_path) or os.getcwd()
        extension = os.path.splitext(self.input_path)[1]
        handle_fd, temp_path = tempfile.mkstemp(prefix='amc_retag_', suffix=extension, dir=directory)
        os.close(handle_fd)

        try:
            cmd = self._build_command(temp_path)
            self.last_command = list(cmd)
            logging.info("Commande FFmpeg (re-tag): %s", ' '.join(cmd))

            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

            process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.PIPE,
                universal_newlines=True, encoding='utf-8', errors='ignore',
                startupinfo=startupinfo, creationflags=subprocess.CREATE_NO_WINDOW,
            )
            try:
                _stdout, stderr_output = process.communicate(timeout=120)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate()
                raise MetadataRetagError("FFmpeg re-tag timed out after 120 seconds")

            if stderr_output:
                for line in stderr_output.strip().splitlines()[-50:]:
                    self.stderr_lines.append(line.strip())

            if process.returncode != 0:
                tail = "\n".join(self.stderr_lines[-30:])
                raise MetadataRetagError(f"FFmpeg error (code {process.returncode}):\n{tail}")

            os.replace(temp_path, self.input_path)
            logging.info("Re-tag in-place réussi : %s", self.input_path)
        except Exception:
            try:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
            except OSError:
                logging.exception("Impossible de supprimer le fichier temporaire de re-tag : %s", temp_path)
            raise
