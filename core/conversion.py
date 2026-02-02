import os
import sys
import subprocess
import signal

class ConversionTask:
    def __init__(self, input_path, output_format, settings=None):
        self.input_path = input_path
        self.output_format = output_format.lower()
        self.settings = settings or {} 
        
        self.output_path = self._generate_output_path()
        self.process = None
        self.is_cancelled = False
        
        self.ffmpeg_exe = self._get_ffmpeg_path()

    def _get_ffmpeg_path(self):
        if getattr(sys, 'frozen', False):
            base_path = sys._MEIPASS
        else:
            base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        
        ffmpeg_path = os.path.join(base_path, 'bin', 'ffmpeg.exe')
        if not os.path.exists(ffmpeg_path):
            raise FileNotFoundError(f"FFmpeg not found at: {ffmpeg_path}")
        return ffmpeg_path

    def _generate_output_path(self):
        base_name = os.path.splitext(self.input_path)[0]
        return f"{base_name}.{self.output_format}"

    def build_command(self):
        cmd = [self.ffmpeg_exe, '-y', '-i', self.input_path]

        # --- Audio Logic ---
        audio_mode = self.settings.get('audio_mode', 'convert')
        
        if audio_mode == 'copy':
            cmd.extend(['-c:a', 'copy'])
        else:
            # Choix Codec
            if self.output_format == 'mp3':
                cmd.extend(['-c:a', 'libmp3lame'])
            elif self.output_format in ['mp4', 'mkv', 'aac', 'm4a']:
                cmd.extend(['-c:a', 'aac'])
            
            # --- CBR vs VBR Logic ---
            rate_mode = self.settings.get('rate_mode', 'cbr')
            
            if rate_mode == 'vbr':
                # VBR utilise -q:a (Quality Scale)
                qscale = self.settings.get('audio_qscale', 4) # Default medium
                cmd.extend(['-q:a', str(qscale)])
            else:
                # CBR utilise -b:a (Bitrate)
                bitrate = self.settings.get('audio_bitrate', '192k')
                # Nettoyage au cas où (enlève le texte "(Radio)")
                if "(" in bitrate:
                    bitrate = bitrate.split("(")[0].strip() # "128k (Radio)" -> "128k"
                
                cmd.extend(['-b:a', bitrate])

        # --- Video Logic ---
        # Si sortie pure audio, pas de vidéo
        if self.output_format in ['mp3', 'wav', 'flac', 'aac', 'm4a', 'ogg']:
            cmd.append('-vn')
        else:
            video_mode = self.settings.get('video_mode', 'convert')
            if video_mode == 'copy':
                cmd.extend(['-c:v', 'copy'])
            else:
                cmd.extend(['-c:v', 'libx264', '-preset', 'fast'])
                crf = self.settings.get('video_crf', 23)
                cmd.extend(['-crf', str(crf)])

        cmd.append(self.output_path)
        return cmd

    def run(self):
        if not os.path.exists(self.input_path):
            raise FileNotFoundError(f"Input not found: {self.input_path}")

        cmd = self.build_command()

        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        
        try:
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.PIPE,
                startupinfo=startupinfo,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            
            stdout, stderr = self.process.communicate()

            if self.process.returncode != 0:
                error_msg = stderr.decode('utf-8', errors='ignore')
                raise RuntimeError(f"FFmpeg Error: {error_msg}")

        except Exception as e:
            if self.is_cancelled:
                return "Cancelled"
            raise e

        return self.output_path

    def stop(self):
        self.is_cancelled = True
        if self.process:
            self.process.kill()