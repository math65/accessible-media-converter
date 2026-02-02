import subprocess
import json
import os
import sys

# CORRECTION ICI : Le nom est MediaMetadata (et pas FileMetadata)
class MediaMetadata:
    def __init__(self, filename, full_path, duration, has_video, audio_codec, video_codec):
        self.filename = filename
        self.full_path = full_path
        self.duration = duration
        self.has_video = has_video
        self.audio_codec = audio_codec
        self.video_codec = video_codec

    def get_summary(self):
        """Retourne un texte court pour l'interface (ex: 'AAC | h264')."""
        info = []
        if self.audio_codec:
            info.append(self.audio_codec.upper())
        
        if self.has_video and self.video_codec:
            info.append(self.video_codec.upper())
        elif self.has_video:
            info.append("Video")
            
        return " + ".join(info) if info else "Unknown"

class FileProber:
    def __init__(self):
        self.ffprobe_exe = self._get_ffprobe_path()

    def _get_ffprobe_path(self):
        if getattr(sys, 'frozen', False):
            base_path = sys._MEIPASS
        else:
            base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        
        ffprobe_path = os.path.join(base_path, 'bin', 'ffprobe.exe')
        if not os.path.exists(ffprobe_path):
            return "ffprobe"
        return ffprobe_path

    def analyze(self, filepath):
        if not os.path.exists(filepath):
            # Utilisation de MediaMetadata ici aussi
            return MediaMetadata(os.path.basename(filepath), filepath, 0, False, None, None)

        cmd = [
            self.ffprobe_exe, 
            '-v', 'quiet', 
            '-print_format', 'json', 
            '-show_format', 
            '-show_streams', 
            filepath
        ]

        try:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            
            output = subprocess.check_output(
                cmd, 
                startupinfo=startupinfo,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            data = json.loads(output)
            
            # 1. Durée
            duration = float(data.get('format', {}).get('duration', 0))
            
            has_video = False
            audio_codec = None
            video_codec = None

            # 2. Analyse des flux (Streams)
            for stream in data.get('streams', []):
                codec_type = stream.get('codec_type')
                
                if codec_type == 'audio':
                    if not audio_codec: # On prend le premier flux audio
                        audio_codec = stream.get('codec_name')
                
                elif codec_type == 'video':
                    # --- DÉTECTION DES POCHETTES ---
                    disposition = stream.get('disposition', {})
                    # Si attached_pic vaut 1, c'est une pochette, pas une vidéo
                    is_cover_art = disposition.get('attached_pic') == 1
                    
                    if not is_cover_art:
                        has_video = True
                        video_codec = stream.get('codec_name')
                    else:
                        # C'est une pochette, on ignore
                        pass

            # Retourne l'objet corrigé MediaMetadata
            return MediaMetadata(
                filename=os.path.basename(filepath),
                full_path=filepath,
                duration=duration,
                has_video=has_video,
                audio_codec=audio_codec,
                video_codec=video_codec
            )

        except Exception as e:
            print(f"Error probing file: {e}")
            return MediaMetadata(os.path.basename(filepath), filepath, 0, False, None, None)