import os
import sys
import subprocess
import json
import logging # Ajout
import builtins


def _translate(msgid):
    translator = builtins.__dict__.get('_')
    if callable(translator):
        return translator(msgid)
    return msgid


def _translatef(msgid, **kwargs):
    return _translate(msgid).format(**kwargs)

class MediaTrack:
    def __init__(self, stream_index, codec_type, codec_name, language='und', title=None, disposition=None):
        self.index = stream_index
        self.codec_type = codec_type
        self.codec_name = codec_name
        self.language = language
        self.title = title
        self.disposition = disposition if disposition else {}

    def is_default(self): return self.disposition.get('default', 0) == 1
    def is_forced(self): return self.disposition.get('forced', 0) == 1
    def is_attached_pic(self): return self.disposition.get('attached_pic', 0) == 1

    def get_summary(self):
        parts = [self.codec_name.upper()]
        if self.language and self.language != 'und': parts.append(self.language.upper())
        if self.title: parts.append(f"\"{self.title}\"")
        return " - ".join(parts)

class MediaMetadata:
    def __init__(self, path):
        self.full_path = path
        self.filename = os.path.basename(path)
        self.duration = 0
        self.size_bytes = 0
        self.video_tracks = []
        self.audio_tracks = []
        self.subtitle_tracks = []
        self.video_codec = ""
        self.audio_codec = ""
        self.width = 0
        self.height = 0
        self.has_video = False 

    @property
    def has_audio(self): return len(self.audio_tracks) > 0
    @property
    def has_subtitles(self): return len(self.subtitle_tracks) > 0

    def get_summary(self):
        v_info = ""
        if self.video_tracks:
            v = self.video_tracks[0]
            v_info = f"{v.codec_name.upper()}"
            if self.width and self.height: v_info += f" ({self.width}x{self.height})"
        
        a_info = ""
        count_a = len(self.audio_tracks)
        if count_a > 0:
            a = self.audio_tracks[0]
            if count_a > 1: a_info = _translatef("{count}x Audio", count=count_a)
            else: a_info = a.codec_name.upper()
        
        s_info = ""
        count_s = len(self.subtitle_tracks)
        if count_s > 0: s_info = _translatef("{count}x Subtitles", count=count_s)

        parts = [x for x in [v_info, a_info, s_info] if x]
        return " / ".join(parts)

class FileProber:
    def __init__(self):
        pass

    def _get_ffprobe_path(self):
        if getattr(sys, 'frozen', False):
            base_path = sys._MEIPASS
        else:
            base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        
        probe_path = os.path.join(base_path, 'bin', 'ffprobe.exe')
        if os.path.exists(probe_path): return probe_path
        return "ffprobe"

    def analyze(self, file_path):
        logging.debug(f"Analyse demandée pour : {file_path}") # LOG
        meta = MediaMetadata(file_path)
        
        if not os.path.exists(file_path):
            logging.error(f"Fichier introuvable : {file_path}") # LOG
            return meta
            
        meta.size_bytes = os.path.getsize(file_path)
        ffprobe = self._get_ffprobe_path()
        logging.debug(f"Utilisation de ffprobe : {ffprobe}") # LOG

        cmd = [
            ffprobe, 
            '-v', 'quiet', 
            '-print_format', 'json', 
            '-show_format', 
            '-show_streams', 
            file_path
        ]
        
        try:
            logging.debug("Exécution commande ffprobe...")
            output = subprocess.check_output(cmd, startupinfo=self._get_startup_info())
            data = json.loads(output)
            
            # LOG DU JSON BRUT (Pour comprendre pourquoi il rate des trucs)
            logging.debug(f"JSON ffprobe reçu (tronqué) : {str(data)[:500]}...") 

            fmt = data.get('format', {})
            try: meta.duration = float(fmt.get('duration', 0))
            except: meta.duration = 0

            streams = data.get('streams', [])
            logging.debug(f"Nombre de flux trouvés : {len(streams)}") # LOG

            for stream in streams:
                idx = stream.get('index')
                c_type = stream.get('codec_type')
                c_name = stream.get('codec_name', 'unknown')
                tags = stream.get('tags', {})
                lang = tags.get('language', 'und')
                title = tags.get('title', None)
                disposition = stream.get('disposition', {})
                
                track = MediaTrack(idx, c_type, c_name, lang, title, disposition)
                
                logging.debug(f"Stream #{idx}: Type={c_type}, Codec={c_name}, Flags={disposition}") # LOG

                if c_type == 'video':
                    if track.is_attached_pic():
                        logging.debug(f" -> Ignoré (Cover art)")
                    else:
                        meta.video_tracks.append(track)
                        meta.has_video = True
                        if meta.width == 0:
                            meta.width = stream.get('width', 0)
                            meta.height = stream.get('height', 0)
                            meta.video_codec = c_name
                        
                elif c_type == 'audio':
                    meta.audio_tracks.append(track)
                    if not meta.audio_codec: meta.audio_codec = c_name
                    
                elif c_type == 'subtitle':
                    meta.subtitle_tracks.append(track)

        except Exception as e:
            logging.error(f"Erreur fatale probing {file_path}", exc_info=True) # LOG CRITIQUE
            
        return meta

    def _get_startup_info(self):
        if os.name == 'nt':
            info = subprocess.STARTUPINFO()
            info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            return info
        return None
