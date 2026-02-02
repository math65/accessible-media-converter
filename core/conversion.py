import os
import subprocess
import sys
import re
import logging # Ajout

class ConversionTask:
    def __init__(self, input_data, target_format, settings, output_dir=None):
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
        self.ffmpeg_exe = self._get_ffmpeg_path()
        self.process = None
        
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

    def run(self, progress_callback=None, stop_check_callback=None):
        ext = self.target_format
        if self.target_format in ['alac', 'aac']: ext = 'm4a'
        
        output_filename = os.path.splitext(os.path.basename(self.input_path))[0] + "." + ext
        
        if self.custom_output_dir and os.path.isdir(self.custom_output_dir):
            output_dir = self.custom_output_dir
        else:
            output_dir = os.path.dirname(self.input_path)
            
        if not os.path.exists(output_dir): os.makedirs(output_dir)  
        output_path = os.path.join(output_dir, output_filename)

        # Construction Commande
        cmd = [self.ffmpeg_exe, '-y', '-i', self.input_path]

        # --- LOGIQUE MULTI-PISTES ---
        track_settings = getattr(self.meta, 'track_settings', None) if self.meta else None
        use_custom_mapping = (track_settings is not None) and (self.target_format in ['mkv', 'mp4', 'mov'])

        if use_custom_mapping:
            logging.info("Utilisation du mapping personnalisé de pistes") # LOG
            
            # VIDEO
            if self.target_format in ['mp4', 'mkv', 'mov']:
                cmd.extend(['-map', '0:v:0'])
            
            # AUDIO
            audio_configs = track_settings.get('audio_tracks', [])
            out_audio_idx = 0
            for track in audio_configs:
                cmd.extend(['-map', f"0:{track['original_index']}"])
                if track['language'] and track['language'] != 'und':
                    cmd.extend([f"-metadata:s:a:{out_audio_idx}", f"language={track['language']}"])
                if track['title']:
                    cmd.extend([f"-metadata:s:a:{out_audio_idx}", f"title={track['title']}"])
                
                dispositions = []
                if track['is_default']: dispositions.append('default')
                if track['is_forced']: dispositions.append('forced')
                val = "+".join(dispositions) if dispositions else "0"
                cmd.extend([f"-disposition:a:{out_audio_idx}", val])
                out_audio_idx += 1

            # SUBS
            sub_configs = track_settings.get('subtitle_tracks', [])
            out_sub_idx = 0
            for track in sub_configs:
                cmd.extend(['-map', f"0:{track['original_index']}"])
                if track['language'] and track['language'] != 'und':
                    cmd.extend([f"-metadata:s:s:{out_sub_idx}", f"language={track['language']}"])
                if track['title']:
                    cmd.extend([f"-metadata:s:s:{out_sub_idx}", f"title={track['title']}"])
                dispositions = []
                if track['is_default']: dispositions.append('default')
                if track['is_forced']: dispositions.append('forced')
                val = "+".join(dispositions) if dispositions else "0"
                cmd.extend([f"-disposition:s:{out_sub_idx}", val])
                out_sub_idx += 1
                
        else:
            logging.debug("Mode automatique (pas de mapping manuel)")

        # --- REGLAGES ---
        audio_mode = self.settings.get('audio_mode', 'convert')
        if audio_mode == 'copy':
            cmd.extend(['-c:a', 'copy'])
        else:
            sr = self.settings.get('audio_sample_rate', 'original')
            if sr != 'original': cmd.extend(['-ar', sr])
            ch = self.settings.get('audio_channels', 'original')
            if ch == '2': cmd.extend(['-ac', '2'])
            elif ch == '1': cmd.extend(['-ac', '1'])

            if self.target_format == 'mp3':
                cmd.extend(['-c:a', 'libmp3lame'])
                if self.settings.get('rate_mode', 'cbr') == 'cbr':
                    cmd.extend(['-b:a', self.settings.get('audio_bitrate', '192k')])
                else:
                    cmd.extend(['-q:a', str(self.settings.get('audio_qscale', 0))])
            elif self.target_format == 'aac':
                cmd.extend(['-c:a', 'aac'])
                if self.settings.get('rate_mode', 'cbr') == 'cbr':
                    cmd.extend(['-b:a', self.settings.get('audio_bitrate', '192k')])
                else:
                    cmd.extend(['-q:a', str(self.settings.get('audio_qscale', 3))])
            elif self.target_format == 'ogg':
                cmd.extend(['-c:a', 'libvorbis', '-q:a', str(self.settings.get('audio_qscale', 6))])
            elif self.target_format == 'wma':
                cmd.extend(['-c:a', 'wmav2', '-b:a', self.settings.get('audio_bitrate', '128k')])
            elif self.target_format == 'wav':
                depth = self.settings.get('audio_bit_depth', 'original')
                codec_map = {'16': 'pcm_s16le', '24': 'pcm_s24le', '32': 'pcm_f32le'}
                cmd.extend(['-c:a', codec_map.get(str(depth), 'pcm_s16le')])
            elif self.target_format == 'flac':
                cmd.extend(['-c:a', 'flac', '-compression_level', str(self.settings.get('flac_compression', 5))])
                depth = self.settings.get('audio_bit_depth', 'original')
                if depth == '16': cmd.extend(['-sample_fmt', 's16'])
                elif depth == '24': cmd.extend(['-sample_fmt', 's32'])
            elif self.target_format == 'alac':
                cmd.extend(['-c:a', 'alac'])
                depth = self.settings.get('audio_bit_depth', 'original')
                if depth == '16': cmd.extend(['-sample_fmt', 's16p'])
                elif depth == '24': cmd.extend(['-sample_fmt', 's32p'])

        if self.target_format in ['mp4', 'mkv', 'mov']:
            video_mode = self.settings.get('video_mode', 'convert')
            if video_mode == 'copy':
                cmd.extend(['-c:v', 'copy'])
            else:
                crf = str(self.settings.get('video_crf', 23))
                cmd.extend(['-c:v', 'libx264', '-crf', crf, '-preset', 'medium'])
        else:
            cmd.append('-vn')

        cmd.append(output_path)

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
                # On log chaque ligne de FFmpeg en DEBUG (ça fait beaucoup mais c'est le but)
                # .strip() pour éviter les sauts de ligne en double
                logging.debug(f"FFmpeg output: {line.strip()}")
                
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
            if stop_check_callback and not stop_check_callback(): 
                logging.error(f"FFmpeg a échoué avec le code {self.process.returncode}")
                raise Exception("FFmpeg error")
        else:
            logging.info("Conversion terminée avec succès.")