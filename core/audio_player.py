"""Lecteur audio par streaming pour l'éditeur de segments (phase 2/3).

Aucune lecture audio n'existait dans l'app ; ce module en ajoute une, taillée pour
la **navigation à l'oreille** d'un fichier potentiellement très long (film 2 h) :

- décodage **à la volée** par le FFmpeg embarqué (``-ss`` puis PCM ``s16le`` stéréo
  44,1 kHz sur stdout) — jamais tout le fichier en RAM, et **tous les formats** de
  l'app sont lisibles (FLAC/Opus/OGG…) ;
- lecture via ``sounddevice`` (``RawOutputStream`` en octets, API hôte MME par
  défaut → **pas de COM**, cf. la leçon accessible_output2 sous Python 3.14) ;
- un seul processus + flux à la fois.

**Annulation non bloquante** : ``play()``/``stop()``/``scrub()`` n'attendent jamais
le thread worker (pas de ``join`` sur le thread UI, sinon chaque pas de flèche du
scrub figerait l'interface). L'annulation passe par un **compteur de génération** :
chaque nouvel appel incrémente ``_generation`` et tue le flux/process courant ; le
worker devenu obsolète le détecte (sa génération ne correspond plus) et se retire
proprement.

Ce module est **wx-agnostique** : les callbacks ``on_position`` / ``on_finished``
sont appelés depuis le thread worker ; l'appelant doit les marshaler vers l'UI
(``wx.CallAfter``). ``seek`` = ``play`` à la nouvelle position (relancer ffmpeg avec
un nouveau ``-ss`` est simple et robuste). Le **scrub** rejoue une courte fenêtre à
chaque pas en annulant la précédente (même discipline d'interruption que
``speak(interrupt=True)``).
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
SCRUB_WINDOW_MS = 200  # durée d'un aperçu de scrub


def _format_ss(ms):
    return f"{max(0, ms) / 1000.0:.3f}"


class _Superseded(Exception):
    """Le worker a été remplacé avant de s'enregistrer."""


class AudioPlayer:
    def __init__(self):
        self._lock = threading.Lock()
        self._generation = 0
        self._process = None
        self._playing = False
        self.ffmpeg_exe = get_ffmpeg_path()

    def is_playing(self):
        with self._lock:
            return self._playing

    def play(self, path, start_ms=0, end_ms=None, on_position=None, on_finished=None):
        """Démarre la lecture depuis ``start_ms`` (jusqu'à ``end_ms`` si fourni),
        en annulant toute lecture en cours. N'attend pas le worker (non bloquant)."""
        with self._lock:
            self._generation += 1
            gen = self._generation
            old_process = self._process
            self._process = None
            self._playing = True
        self._kill(old_process)
        threading.Thread(
            target=self._run,
            args=(path, int(start_ms), end_ms, on_position, on_finished, gen),
            daemon=True, name="audio-player",
        ).start()

    def scrub(self, path, pos_ms, window_ms=SCRUB_WINDOW_MS):
        """Rejoue une courte fenêtre à ``pos_ms`` (aperçu façon scrub REAPER),
        en coupant l'aperçu précédent."""
        self.play(path, start_ms=int(pos_ms), end_ms=int(pos_ms) + int(window_ms))

    def stop(self):
        """Interrompt toute lecture (idempotent, non bloquant)."""
        with self._lock:
            self._generation += 1
            old_process = self._process
            self._process = None
            self._playing = False
        self._kill(old_process)

    @staticmethod
    def _kill(process):
        # On ne tue QUE le process ffmpeg (thread-safe). Le flux sounddevice n'est
        # jamais touché depuis un autre thread — PortAudio n'est pas thread-safe et
        # un abort()/close() concurrent d'un write() en cours crashe en natif.
        # Tuer ffmpeg provoque un EOF sur stdout : le worker sort de sa boucle et
        # ferme lui-même son propre flux.
        if process is not None and process.poll() is None:
            try:
                process.kill()
            except Exception:
                pass

    # ------------------------------------------------------------------ worker
    def _run(self, path, start_ms, end_ms, on_position, on_finished, gen):
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
            # Enregistrement du process (pour que stop()/play() puisse le tuer) : si
            # on a déjà été remplacé, on abandonne (le finally tue notre process).
            with self._lock:
                if gen != self._generation:
                    raise _Superseded
                self._process = process

            # latency='low' : réduit le pré-remplissage du tampon → démarrage plus
            # réactif (l'arrêt net est géré par abort() dans le finally).
            stream = sd.RawOutputStream(
                samplerate=SAMPLE_RATE, channels=CHANNELS, dtype='int16', latency='low')
            stream.start()
            bytes_written = 0
            last_report_ms = -_POSITION_INTERVAL_MS
            while True:
                with self._lock:
                    if gen != self._generation:
                        break  # remplacé / stoppé → sortie non bloquante
                data = process.stdout.read(_READ_CHUNK)
                if not data:
                    with self._lock:
                        completed = gen == self._generation  # EOF réel, pas un kill
                    break
                stream.write(data)  # bloque → cale la lecture sur le temps réel
                bytes_written += len(data)

                if on_position is not None:
                    played_ms = bytes_written / BYTES_PER_MS
                    if played_ms - last_report_ms >= _POSITION_INTERVAL_MS:
                        last_report_ms = played_ms
                        on_position(int(start_ms + played_ms))

            if completed:
                # Laisse le tampon PortAudio se vider avant de fermer (sinon la fin
                # est coupée), puis signale la position finale.
                try:
                    import time as _time
                    _time.sleep(float(getattr(stream, 'latency', 0.0)) + 0.05)
                except Exception:
                    pass
                if on_position is not None:
                    on_position(int(start_ms + bytes_written / BYTES_PER_MS))
        except _Superseded:
            pass
        except Exception:
            logging.exception("AudioPlayer : erreur pendant la lecture.")
        finally:
            if stream is not None:
                try:
                    # Fin naturelle : stop() laisse le tampon se vider. Annulation
                    # (pause/stop/scrub) : abort() coupe net → pas de latence d'arrêt.
                    # (Même thread que la création du flux → sûr pour PortAudio.)
                    if completed:
                        stream.stop()
                    else:
                        stream.abort()
                    stream.close()
                except Exception:
                    pass
            if process is not None and process.poll() is None:
                try:
                    process.kill()
                except Exception:
                    pass
            with self._lock:
                still_current = gen == self._generation
                if still_current:
                    self._process = None
                    self._playing = False
            if completed and still_current and on_finished is not None:
                on_finished()
