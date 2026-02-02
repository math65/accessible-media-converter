import os
import sys
import subprocess
import json

class MediaMetadata:
    """
    Data structure to hold file information.
    """
    def __init__(self):
        self.filename = ""
        self.full_path = ""  # <--- CRITICAL: Full path for FFmpeg
        self.duration_sec = 0.0
        self.format_long = ""  
        self.size_bytes = 0
        
        # Video Info
        self.has_video = False
        self.video_codec = ""
        self.video_resolution = "" 
        
        # Audio Info
        self.has_audio = False
        self.audio_codec = ""
        self.audio_bitrate = "" 
        self.audio_channels = 0 

    def get_summary(self):
        """Returns a short string description for the UI list."""
        parts = []
        if self.has_video:
            parts.append(f"Video: {self.video_codec} ({self.video_resolution})")
        if self.has_audio:
            parts.append(f"Audio: {self.audio_codec} {self.audio_bitrate}")
        
        if not parts:
            return "Unknown / No Stream"
        return " | ".join(parts)

class FileProber:
    """
    Wrapper around ffprobe to analyze media files.
    """
    def __init__(self):
        self.ffprobe_exe = self._get_ffprobe_path()

    def _get_ffprobe_path(self):
        if getattr(sys, 'frozen', False):
            base_path = sys._MEIPASS
        else:
            base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        
        ffprobe_path = os.path.join(base_path, 'bin', 'ffprobe.exe')
        
        if not os.path.exists(ffprobe_path):
            raise FileNotFoundError(f"FFprobe binary not found at: {ffprobe_path}")
            
        return ffprobe_path

    def analyze(self, file_path):
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        cmd = [
            self.ffprobe_exe,
            '-v', 'quiet',
            '-print_format', 'json',
            '-show_format',
            '-show_streams',
            file_path
        ]

        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        
        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                startupinfo=startupinfo,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            stdout, stderr = process.communicate()
            
            if process.returncode != 0:
                raise RuntimeError("FFprobe failed to analyze file")
                
            data = json.loads(stdout)
            return self._parse_json(data, file_path)

        except Exception as e:
            meta = MediaMetadata()
            meta.filename = os.path.basename(file_path)
            meta.full_path = file_path # Keep path even on error
            meta.format_long = "Error reading file"
            return meta

    def _parse_json(self, data, file_path):
        meta = MediaMetadata()
        meta.filename = os.path.basename(file_path)
        meta.full_path = file_path # <--- Store full path
        
        fmt = data.get('format', {})
        meta.duration_sec = float(fmt.get('duration', 0))
        meta.size_bytes = int(fmt.get('size', 0))
        meta.format_long = fmt.get('format_long_name', 'Unknown')

        for stream in data.get('streams', []):
            codec_type = stream.get('codec_type')
            
            if codec_type == 'video':
                meta.has_video = True
                meta.video_codec = stream.get('codec_name', 'unknown')
                w = stream.get('width', 0)
                h = stream.get('height', 0)
                if w and h:
                    meta.video_resolution = f"{w}x{h}"
            
            elif codec_type == 'audio':
                if not meta.has_audio:
                    meta.has_audio = True
                    meta.audio_codec = stream.get('codec_name', 'unknown')
                    meta.audio_channels = int(stream.get('channels', 0))
                    br = stream.get('bit_rate')
                    if br:
                        kbps = int(br) // 1000
                        meta.audio_bitrate = f"{kbps}k"
                    else:
                        meta.audio_bitrate = ""

        return meta