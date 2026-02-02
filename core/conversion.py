import os
import subprocess
import sys
import re

class ConversionTask:
    def __init__(self, input_path, target_format, settings, duration=0):
        self.input_path = input_path
        self.target_format = target_format
        self.settings = settings
        self.duration = float(duration) if duration else 0.0 # Force le float
        self.ffmpeg_exe = self._get_ffmpeg_path()

    def _get_ffmpeg_path(self):
        if getattr(sys, 'frozen', False):
            base_path = sys._MEIPASS
        else:
            base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        
        ffmpeg_path = os.path.join(base_path, 'bin', 'ffmpeg.exe')
        if not os.path.exists(ffmpeg_path):
            return "ffmpeg"
        return ffmpeg_path

    def run(self, progress_callback=None):
        output_filename = os.path.splitext(os.path.basename(self.input_path))[0] + "." + self.target_format
        output_dir = os.path.dirname(self.input_path)
        output_path = os.path.join(output_dir, output_filename)

        cmd = [self.ffmpeg_exe, '-y', '-i', self.input_path]

        # --- LOGIQUE AUDIO ---
        audio_mode = self.settings.get('audio_mode', 'convert')
        if audio_mode == 'copy':
            cmd.extend(['-c:a', 'copy'])
        else:
            if self.target_format == 'mp3':
                cmd.extend(['-c:a', 'libmp3lame'])
            elif self.target_format in ['aac', 'm4a', 'mp4']:
                cmd.extend(['-c:a', 'aac'])
            
            rate_mode = self.settings.get('rate_mode', 'cbr')
            if rate_mode == 'cbr':
                bitrate = self.settings.get('audio_bitrate', '192k')
                cmd.extend(['-b:a', bitrate])
            else:
                qscale = str(self.settings.get('audio_qscale', 4))
                if self.target_format == 'mp3':
                    cmd.extend(['-q:a', qscale])
                else:
                    cmd.extend(['-q:a', qscale])

        # --- LOGIQUE VIDÉO ---
        if self.target_format in ['mp4', 'mkv']:
            video_mode = self.settings.get('video_mode', 'convert')
            if video_mode == 'copy':
                cmd.extend(['-c:v', 'copy'])
            else:
                crf = str(self.settings.get('video_crf', 23))
                cmd.extend(['-c:v', 'libx264', '-crf', crf, '-preset', 'medium'])
        else:
            cmd.append('-vn')

        cmd.append(output_path)

        # --- EXÉCUTION ---
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.PIPE,
            universal_newlines=True,
            encoding='utf-8',
            errors='ignore', # CRITIQUE : Ignore les erreurs d'accent console Windows
            startupinfo=startupinfo,
            creationflags=subprocess.CREATE_NO_WINDOW
        )

        time_pattern = re.compile(r'time=(\d{2}):(\d{2}):(\d{2}\.\d+)')

        while True:
            line = process.stderr.readline()
            if not line and process.poll() is not None:
                break
            
            if line and progress_callback:
                match = time_pattern.search(line)
                if match:
                    # Protection contre Division par Zéro
                    if self.duration > 0:
                        try:
                            h, m, s = match.groups()
                            current_seconds = int(h) * 3600 + int(m) * 60 + float(s)
                            percent = int((current_seconds / self.duration) * 100)
                            percent = min(max(percent, 0), 100)
                            progress_callback(percent)
                        except:
                            pass # On ignore les erreurs de calcul mathématique
                    else:
                        # Si pas de durée connue, on peut envoyer une valeur fictive ou rien
                        pass

        if process.returncode != 0:
            raise Exception("FFmpeg returned error code")