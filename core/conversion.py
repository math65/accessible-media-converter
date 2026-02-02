import os
import subprocess
import sys
import re

class ConversionTask:
    def __init__(self, input_path, target_format, settings, duration=0, output_dir=None):
        self.input_path = input_path
        self.target_format = target_format
        self.settings = settings
        self.duration = float(duration) if duration else 0.0
        self.custom_output_dir = output_dir
        self.ffmpeg_exe = self._get_ffmpeg_path()
        self.process = None

    def _get_ffmpeg_path(self):
        if getattr(sys, 'frozen', False):
            base_path = sys._MEIPASS
        else:
            base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        
        ffmpeg_path = os.path.join(base_path, 'bin', 'ffmpeg.exe')
        if not os.path.exists(ffmpeg_path): return "ffmpeg"
        return ffmpeg_path

    def run(self, progress_callback=None, stop_check_callback=None):
        # GESTION EXTENSION
        # On force .m4a pour l'ALAC (Apple Lossless) ET pour l'AAC
        ext = self.target_format
        if self.target_format in ['alac', 'aac']: 
            ext = 'm4a'
        
        output_filename = os.path.splitext(os.path.basename(self.input_path))[0] + "." + ext
        
        if self.custom_output_dir and os.path.isdir(self.custom_output_dir):
            output_dir = self.custom_output_dir
        else:
            output_dir = os.path.dirname(self.input_path)
            
        if not os.path.exists(output_dir): os.makedirs(output_dir)  
        output_path = os.path.join(output_dir, output_filename)

        cmd = [self.ffmpeg_exe, '-y', '-i', self.input_path]

        # --- AUDIO ---
        audio_mode = self.settings.get('audio_mode', 'convert')
        
        if audio_mode == 'copy':
            cmd.extend(['-c:a', 'copy'])
        else:
            # 1. SAMPLE RATE (Commun à tous)
            sr = self.settings.get('audio_sample_rate', 'original')
            if sr != 'original':
                cmd.extend(['-ar', sr])

            # 2. CODECS & OPTIONS SPECIFIQUES
            if self.target_format == 'mp3':
                cmd.extend(['-c:a', 'libmp3lame'])
                rate_mode = self.settings.get('rate_mode', 'cbr')
                if rate_mode == 'cbr':
                    cmd.extend(['-b:a', self.settings.get('audio_bitrate', '192k')])
                else:
                    # VBR MP3: -q:a 0(best) à 9(worst)
                    q = str(self.settings.get('audio_qscale', 0))
                    cmd.extend(['-q:a', q])
                
            elif self.target_format == 'aac':
                cmd.extend(['-c:a', 'aac'])
                rate_mode = self.settings.get('rate_mode', 'cbr')
                if rate_mode == 'cbr':
                    cmd.extend(['-b:a', self.settings.get('audio_bitrate', '192k')])
                else:
                    # VBR AAC: -q:a 1(worst) à 5(best)
                    q = str(self.settings.get('audio_qscale', 3))
                    cmd.extend(['-q:a', q])
                
            elif self.target_format == 'wav':
                # WAV (PCM)
                depth = self.settings.get('audio_bit_depth', 'original')
                if depth == '16': codec = 'pcm_s16le'
                elif depth == '24': codec = 'pcm_s24le'
                elif depth == '32': codec = 'pcm_f32le'
                else: codec = 'pcm_s16le'
                cmd.extend(['-c:a', codec])
                
            elif self.target_format == 'flac':
                cmd.extend(['-c:a', 'flac'])
                # Compression Level (0-8)
                comp = str(self.settings.get('flac_compression', 5))
                cmd.extend(['-compression_level', comp])
                
                # Bit Depth via sample_fmt
                depth = self.settings.get('audio_bit_depth', 'original')
                if depth == '16': cmd.extend(['-sample_fmt', 's16'])
                elif depth == '24': cmd.extend(['-sample_fmt', 's32'])
                
            elif self.target_format == 'alac':
                cmd.extend(['-c:a', 'alac'])
                # Bit Depth via sample_fmt
                depth = self.settings.get('audio_bit_depth', 'original')
                if depth == '16': cmd.extend(['-sample_fmt', 's16p'])
                elif depth == '24': cmd.extend(['-sample_fmt', 's32p'])

        # --- VIDEO ---
        if self.target_format in ['mp4', 'mkv']:
            video_mode = self.settings.get('video_mode', 'convert')
            if video_mode == 'copy':
                cmd.extend(['-c:v', 'copy'])
            else:
                crf = str(self.settings.get('video_crf', 23))
                cmd.extend(['-c:v', 'libx264', '-crf', crf, '-preset', 'medium'])
        else:
            # Si format audio pur, on désactive la vidéo
            cmd.append('-vn')

        cmd.append(output_path)

        # --- EXÉCUTION ---
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        
        self.process = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.PIPE,
            universal_newlines=True, encoding='utf-8', errors='ignore',
            startupinfo=startupinfo, creationflags=subprocess.CREATE_NO_WINDOW
        )

        time_pattern = re.compile(r'time=(\d{2}):(\d{2}):(\d{2}\.\d+)')
        while True:
            # Vérification Arrêt Utilisateur
            if stop_check_callback and stop_check_callback():
                self.process.kill()
                raise Exception("Stopped by user")

            line = self.process.stderr.readline()
            if not line and self.process.poll() is not None: break
            
            if line and progress_callback:
                match = time_pattern.search(line)
                if match and self.duration > 0:
                    try:
                        h, m, s = match.groups()
                        current_seconds = int(h) * 3600 + int(m) * 60 + float(s)
                        percent = int((current_seconds / self.duration) * 100)
                        percent = min(max(percent, 0), 100)
                        progress_callback(percent)
                    except: pass

        if self.process.returncode != 0:
            # Si ce n'est pas un arrêt volontaire, c'est une erreur
            if stop_check_callback and not stop_check_callback(): 
                raise Exception("FFmpeg error")