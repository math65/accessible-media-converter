"""Lecteur audio par streaming pour l'éditeur de segments (phase 2/3).

Aucune lecture audio n'existait dans l'app ; ce module en ajoute une, taillée pour
la **navigation à l'oreille** d'un fichier potentiellement très long (film 2 h) :

- décodage **à la volée** par le FFmpeg embarqué (``-ss`` puis PCM ``s16le`` stéréo
  44,1 kHz sur stdout) — jamais tout le fichier en RAM, et **tous les formats** de
  l'app sont lisibles (FLAC/Opus/OGG…) ;
- lecture via ``sounddevice`` (``RawOutputStream`` en octets, API hôte MME par
  défaut → **pas de COM**, cf. la leçon accessible_output2 sous Python 3.14) ;
- un seul processus + flux à la fois (verrou), ``stop()`` tue ffmpeg et ferme le flux.

Ce module est **wx-agnostique** : les callbacks ``on_position`` / ``on_finished``
sont appelés depuis le thread worker ; l'appelant doit les marshaler vers l'UI
(``wx.CallAfter``). ``seek`` = ``stop`` + ``play`` à la nouvelle position (relancer
ffmpeg avec un nouveau ``-ss`` est simple et robuste ; la latence convient au
clavier). Le scrub (phase 3) réutilisera ce socle par courtes fenêtres.
"""

import logging
import subprocess
import threading

from core.ffmpeg_helpers import get_ffmpeg_path


SAMPLE_RATE = 44100
CHANNELS = 2
BYTES_PER_SAMPLE = 2  # s16le
BYTES_PER_MS = SAMPLE_RATE * CHANNELS * BYTES_PER_SAMPLE / 1000.0
_READ_CHUNK = 8192  # octets lus par itération (~46 ms stéréo 16 bits)
_POSITION_INTERVAL_MS = 100  # cadence de remontée du playhead (~10 Hz)


def _format_ss(ms):
    return f"{max(0, ms) / 1000.0:.3f}"


class AudioPlayer:
    def __init__(self):
        self._lock = threading.Lock()
        self._thread = None
        self._stop_event = threading.Event()
        self._process = None
        self._stream = None
        self._playing = False
        self.ffmpeg_exe = get_ffmpeg_path()

    def is_playing(self):
        return self._playing

    def play(self, path, start_ms=0, end_ms=None, on_position=None, on_finished=None):
        """Démarre la lecture depuis ``start_ms`` (jusqu'à ``end_ms`` si fourni).
        Coupe toute lecture en cours au préalable (un seul flux à la fois)."""
        self.stop()
        with self._lock:
            self._stop_event = threading.Event()
            self._playing = True
            self._thread = threading.Thread(
                target=self._run,
                args=(path, int(start_ms), end_ms, on_position, on_finished),
                daemon=True,
                name="audio-player",
            )
            self._thread.start()

    def stop(self):
        """Interrompt la lecture (idempotent). Bloque brièvement le temps que le
        thread worker libère ffmpeg et le flux."""
        with self._lock:
            thread = self._thread
            self._stop_event.set()
            process = self._process
        if process is not None and process.poll() is None:
            try:
                process.kill()
            except Exception:
                logging.exception("AudioPlayer : impossible de tuer ffmpeg.")
        if thread is not None and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=1.0)

    # ------------------------------------------------------------------ worker
    def _run(self, path, start_ms, end_ms, on_position, on_finished):
        import sounddevice as sd  # import tardif : évite de charger PortAudio au démarrage

        cmd = [self.ffmpeg_exe, '-hide_banner', '-loglevel', 'quiet',
               '-ss', _format_ss(start_ms), '-i', path]
        if end_ms is not None and end_ms > start_ms:
            cmd.extend(['-t', _format_ss(end_ms - start_ms)])
        cmd.extend(['-vn', '-f', 's16le', '-acodec', 'pcm_s16le',
                    '-ac', str(CHANNELS), '-ar', str(SAMPLE_RATE), '-'])

        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        process = None
        stream = None
        completed = False
        try:
            process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                startupinfo=startupinfo, creationflags=subprocess.CREATE_NO_WINDOW,
            )
            with self._lock:
                self._process = process

            stream = sd.RawOutputStream(samplerate=SAMPLE_RATE, channels=CHANNELS, dtype='int16')
            with self._lock:
                self._stream = stream
            stream.start()

            bytes_written = 0
            last_report_ms = -_POSITION_INTERVAL_MS
            while not self._stop_event.is_set():
                data = process.stdout.read(_READ_CHUNK)
                if not data:
                    completed = True
                    break
                stream.write(data)  # bloque → cale la lecture sur le temps réel
                bytes_written += len(data)

                if on_position is not None:
                    played_ms = bytes_written / BYTES_PER_MS
                    if played_ms - last_report_ms >= _POSITION_INTERVAL_MS:
                        last_report_ms = played_ms
                        on_position(int(start_ms + played_ms))

            if completed and not self._stop_event.is_set():
                # Laisse le tampon PortAudio se vider avant de fermer (sinon la fin
                # est coupée), puis signale la position finale.
                try:
                    import time as _time
                    _time.sleep(float(getattr(stream, 'latency', 0.0)) + 0.05)
                except Exception:
                    pass
                if on_position is not None:
                    on_position(int(start_ms + bytes_written / BYTES_PER_MS))
        except Exception:
            logging.exception("AudioPlayer : erreur pendant la lecture.")
        finally:
            if stream is not None:
                try:
                    stream.stop(); stream.close()
                except Exception:
                    pass
            if process is not None and process.poll() is None:
                try:
                    process.kill()
                except Exception:
                    pass
            with self._lock:
                self._process = None
                self._stream = None
                self._playing = False
            if completed and not self._stop_event.is_set() and on_finished is not None:
                on_finished()
