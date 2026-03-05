"""
audio_engine.py – Capture audio asynchrone : microphone + loopback système.

Architecture
------------
* Le microphone est capturé via ``sounddevice`` (cross-platform).
* Le loopback (son des haut-parleurs / de la visio) est capturé via ``soundcard``
  qui utilise l'API WASAPI en mode loopback sur Windows.
* Chaque chunk PCM 16-bit est encodé en Base64 puis déposé dans une
  ``asyncio.Queue`` partagée avec le client WebSocket Gemini.
* Les captures tournent dans des threads dédiés pour ne pas bloquer la boucle
  asyncio ni l'UI Qt.

Notes de configuration loopback
--------------------------------
Windows (recommandé) :
    soundcard utilise WASAPI loopback automatiquement via
    ``sc.get_microphone(id=<nom_haut_parleur>, include_loopback=True)``.
    Aucune configuration système supplémentaire n'est nécessaire.

Linux :
    PulseAudio/PipeWire crée automatiquement des sources « monitor » pour
    chaque périphérique de sortie.  Listez-les avec :
        pactl list short sources | grep monitor
    Puis définissez la variable d'environnement :
        export LOOPBACK_DEVICE="alsa_output.pci-0000_00_1f.3.analog-stereo.monitor"
    sounddevice utilisera ce nom comme périphérique d'entrée.

macOS :
    Installez un périphérique audio virtuel comme BlackHole (gratuit) ou
    Soundflower.  Dans Paramètres Système → Son, sélectionnez ce périphérique
    comme sortie, puis passez son nom dans LOOPBACK_DEVICE.
"""

import asyncio
import base64
import os
import queue
import sys
import threading
import warnings

import numpy as np
import sounddevice as sd

# Compatibilité NumPy 2.x : le mode binaire de numpy.fromstring a été supprimé.
# soundcard utilise encore fromstring(buffer, dtype=…) ; on redirige vers frombuffer.
_FROMSTRING_PATCHED = False
if not _FROMSTRING_PATCHED:
    _orig_fromstring = np.fromstring

    def _compat_fromstring(string, dtype=float, count=-1, sep=""):
        if sep == "":
            # binary mode: frombuffer is the direct replacement; 'offset' defaults to 0
            return np.frombuffer(string, dtype=dtype, count=count)
        return _orig_fromstring(string, dtype=dtype, count=count, sep=sep)

    np.fromstring = _compat_fromstring
    _FROMSTRING_PATCHED = True

_SOUNDCARD_AVAILABLE = False
try:
    import soundcard as sc  # noqa: F401
    _SOUNDCARD_AVAILABLE = True
except Exception:  # ImportError ou OSError si pas de WASAPI
    pass

from config import AUDIO_FORMAT, CHANNELS, CHUNK_SIZE, SAMPLE_RATE


class AudioEngine:
    """
    Gère la capture simultanée du microphone et du loopback système.

    Usage::

        engine = AudioEngine(loop=asyncio.get_event_loop(), audio_queue=queue)
        engine.start()   # démarre les threads de capture
        # … traitement …
        engine.stop()    # arrête proprement les threads
    """

    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        audio_queue: "asyncio.Queue[str]",
    ) -> None:
        self._loop = loop
        self._queue = audio_queue
        self._running = False
        self._threads: list[threading.Thread] = []
        self._dropped_chunks: int = 0  # compteur pour le monitoring

    # ------------------------------------------------------------------
    # Utilitaire partagé – injection thread-safe
    # ------------------------------------------------------------------

    def _safe_enqueue(self, encoded: str) -> None:
        """
        Dépose un chunk base64 dans la queue depuis le thread asyncio.
        Si la queue est pleine, le chunk est silencieusement abandonné
        (log périodique toutes les 100 pertes pour éviter le flood).
        """
        try:
            self._queue.put_nowait(encoded)
        except asyncio.QueueFull:
            self._dropped_chunks += 1
            if self._dropped_chunks % 100 == 1:
                print(
                    f"[Audio] Queue pleine : {self._dropped_chunks} chunk(s) abandonnés. "
                    "Réseau trop lent ou Gemini déconnecté ?"
                )

    # ------------------------------------------------------------------
    # Microphone (sounddevice – cross-platform)
    # ------------------------------------------------------------------

    def _mic_callback(self, indata: np.ndarray, frames: int, time, status) -> None:
        """Callback sounddevice appelé à chaque bloc audio du micro."""
        if status:
            print(f"[Audio/Mic] {status}")
        # Conversion en PCM int16 puis encodage base64
        pcm_bytes = indata.copy().astype(np.int16).tobytes()
        encoded = base64.b64encode(pcm_bytes).decode("utf-8")
        # qasync + PyQt6 (notamment sous Python 3.14) peut lever
        # une erreur de signature quand on passe des *args à
        # call_soon_threadsafe. On encapsule donc l'appel dans un
        # callback sans argument.
        self._loop.call_soon_threadsafe(lambda: self._safe_enqueue(encoded))

    def _capture_mic(self) -> None:
        """Boucle de capture micro – tourne dans un thread dédié."""
        with sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype=AUDIO_FORMAT,
            blocksize=CHUNK_SIZE,
            callback=self._mic_callback,
        ):
            while self._running:
                sd.sleep(100)  # laisse le callback travailler

    # ------------------------------------------------------------------
    # Loopback système (soundcard / WASAPI)
    # ------------------------------------------------------------------

    def _loopback_callback(self, indata: np.ndarray, frames: int, time, status) -> None:
        """Callback dédié au flux loopback sounddevice (float32 ou int16)."""
        if status:
            print(f"[Audio/Loopback] {status}")
        # WASAPI loopback renvoie souvent du float32 même si on demande int16 ;
        # on normalise explicitement pour les deux cas.
        if indata.dtype == np.float32:
            pcm_bytes = (np.clip(indata, -1.0, 1.0) * 32767).astype(np.int16).tobytes()
        else:
            pcm_bytes = indata.copy().astype(np.int16).tobytes()
        encoded = base64.b64encode(pcm_bytes).decode("utf-8")
        self._loop.call_soon_threadsafe(lambda: self._safe_enqueue(encoded))

    def _capture_windows_loopback_sounddevice(self) -> bool:
        """
        Fallback Windows : capture loopback via sounddevice/WASAPI.

        Utile quand la lib soundcard n'est pas disponible.
        Retourne True si la capture a démarré et s'est terminée proprement,
        False si aucun périphérique loopback WASAPI n'a pu être ouvert.

        Ordre de priorité :
        1. Périphériques d'entrée dont le nom contient « loopback » (certains
           pilotes WASAPI les exposent directement comme source d'entrée).
        2. Périphérique de sortie par défaut du système.
        3. Tous les autres périphériques de sortie.
        """
        if not sys.platform.startswith("win"):
            return False

        wasapi_settings = getattr(sd, "WasapiSettings", None)
        if wasapi_settings is None:
            return False

        try:
            devices = sd.query_devices()
        except Exception as exc:
            print(f"[Audio/Loopback] Impossible de lister les périphériques WASAPI : {exc}")
            return False

        # Identifie le périphérique de sortie par défaut (peut être None).
        try:
            default_out_idx = sd.default.device[1]
        except Exception:
            default_out_idx = None

        # Construit la liste ordonnée : loopback-nommés → sortie défaut → autres sorties.
        loopback_named: list[tuple[int, dict]] = []
        default_out: list[tuple[int, dict]] = []
        other_out: list[tuple[int, dict]] = []

        for device_id, dev in enumerate(devices):
            name_lower = dev.get("name", "").lower()
            if "loopback" in name_lower and dev.get("max_input_channels", 0) >= 1:
                loopback_named.append((device_id, dev))
            elif dev.get("max_output_channels", 0) >= 1:
                if device_id == default_out_idx:
                    default_out.append((device_id, dev))
                else:
                    other_out.append((device_id, dev))

        candidates = loopback_named + default_out + other_out

        for device_id, dev in candidates:
            is_loopback_named = "loopback" in dev.get("name", "").lower()
            # Les périphériques loopback-nommés sont déjà des sources d'entrée ;
            # on les ouvre sans WasapiSettings(loopback=True).
            open_kwargs: dict = dict(
                device=device_id,
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                blocksize=CHUNK_SIZE,
                callback=self._loopback_callback,
            )
            if not is_loopback_named:
                open_kwargs["extra_settings"] = wasapi_settings(loopback=True)

            # Essaie float32 en priorité (format natif WASAPI loopback), puis
            # AUDIO_FORMAT si différent (evite de tenter deux fois le même type).
            dtypes_to_try = ["float32"]
            if AUDIO_FORMAT != "float32":
                dtypes_to_try.append(AUDIO_FORMAT)
            for dtype in dtypes_to_try:
                open_kwargs["dtype"] = dtype
                try:
                    with sd.InputStream(**open_kwargs):
                        print(
                            "[Audio/Loopback] WASAPI loopback via sounddevice actif sur : "
                            f"{dev.get('name', device_id)}"
                        )
                        while self._running:
                            sd.sleep(100)
                    return True
                except Exception:
                    continue

        return False

    def _capture_loopback(self) -> None:
        """
        Capture le son sortant des haut-parleurs (loopback).

        La méthode essaie d'abord soundcard (WASAPI loopback).
        Si soundcard n'est pas disponible ou échoue, elle tente d'utiliser
        la variable d'environnement LOOPBACK_DEVICE avec sounddevice
        (pratique sur Linux avec les sources monitor PulseAudio/PipeWire).
        """
        # --- Tentative 1 : soundcard (Windows WASAPI loopback) ---
        if _SOUNDCARD_AVAILABLE:
            try:
                speaker = sc.default_speaker()
                # include_loopback=True active le mode WASAPI loopback
                loopback_mic = sc.get_microphone(
                    id=str(speaker.name), include_loopback=True
                )

                # Offload encoding to a dedicated worker thread so that the
                # recording loop returns to recorder.record() as fast as
                # possible, reducing WASAPI buffer overflow and the resulting
                # "data discontinuity" warnings.
                raw_queue: queue.Queue = queue.Queue(maxsize=64)
                # Log a discontinuity warning every N occurrences to avoid
                # flooding the console; still visible but not overwhelming.
                DISCONTINUITY_LOG_INTERVAL = 20
                # Seconds to wait for the encoder thread to flush and exit.
                ENCODER_THREAD_SHUTDOWN_TIMEOUT = 1.0

                def _encoder_worker() -> None:
                    while True:
                        item = raw_queue.get()
                        if item is None:
                            break
                        pcm = (np.clip(item, -1.0, 1.0) * 32767).astype(np.int16)
                        enc = base64.b64encode(pcm.tobytes()).decode("utf-8")
                        # Use a default-argument capture to avoid the classic
                        # late-binding lambda closure bug.
                        self._loop.call_soon_threadsafe(
                            lambda e=enc: self._safe_enqueue(e)
                        )

                enc_thread = threading.Thread(
                    target=_encoder_worker, name="loopback-encoder", daemon=True
                )
                enc_thread.start()

                # blocksize sets the internal WASAPI buffer size (in frames).
                # A larger value gives the OS more headroom before flagging a
                # discontinuity when the Python thread is briefly preempted.
                recorder_blocksize = CHUNK_SIZE * 4
                _discontinuity_count = 0
                try:
                    # warnings.catch_warnings() saves and automatically
                    # restores warnings.showwarning (and the filter list) on
                    # exit — even if an exception is raised — so no explicit
                    # finally-restore is needed.
                    with warnings.catch_warnings():
                        # Replace showwarning once for the entire recording
                        # session instead of wrapping every recorder.record()
                        # call in catch_warnings(record=True).  Removing that
                        # per-iteration context-manager overhead keeps the
                        # tight loop fast enough to prevent WASAPI buffer
                        # overflows that trigger "data discontinuity".
                        _original_showwarning = warnings.showwarning

                        def _discontinuity_handler(
                            msg, cat, fn, ln, file=None, line=None
                        ):
                            nonlocal _discontinuity_count
                            if issubclass(cat, sc.SoundcardRuntimeWarning):
                                _discontinuity_count += 1
                                if (
                                    _discontinuity_count
                                    % DISCONTINUITY_LOG_INTERVAL
                                    == 1
                                ):
                                    print(
                                        f"[Audio/Loopback] data discontinuity "
                                        f"(×{_discontinuity_count}) – "
                                        "charge système élevée ou pilote audio lent."
                                    )
                            else:
                                _original_showwarning(msg, cat, fn, ln, file, line)

                        warnings.showwarning = _discontinuity_handler
                        warnings.simplefilter("always", sc.SoundcardRuntimeWarning)

                        with loopback_mic.recorder(
                            samplerate=SAMPLE_RATE,
                            channels=CHANNELS,
                            blocksize=recorder_blocksize,
                        ) as recorder:
                            print(
                                f"[Audio/Loopback] WASAPI loopback actif sur : {speaker.name}"
                            )
                            while self._running:
                                # recorder.record() returns a float32 array
                                # normalised to [-1, 1]; no per-call warning
                                # context manager needed any more.
                                data = recorder.record(numframes=CHUNK_SIZE)
                                try:
                                    raw_queue.put_nowait(data)
                                except queue.Full:
                                    pass  # drop frame; encoder is falling behind
                finally:
                    raw_queue.put(None)  # stop encoder thread
                    enc_thread.join(timeout=ENCODER_THREAD_SHUTDOWN_TIMEOUT)
                return  # succès → on ne passe pas aux alternatives
            except Exception as exc:
                print(
                    f"[Audio/Loopback] soundcard échoue ({exc}). "
                    "Tentative WASAPI sounddevice puis LOOPBACK_DEVICE…"
                )

        # --- Tentative 2 : fallback Windows sounddevice/WASAPI loopback ---
        if self._capture_windows_loopback_sounddevice():
            return

        # --- Tentative 3 : sounddevice + LOOPBACK_DEVICE (Linux/macOS) ---
        loopback_device = os.environ.get("LOOPBACK_DEVICE")
        if loopback_device:
            try:
                print(f"[Audio/Loopback] Utilisation du périphérique : {loopback_device}")
                with sd.InputStream(
                    device=loopback_device,
                    samplerate=SAMPLE_RATE,
                    channels=CHANNELS,
                    dtype=AUDIO_FORMAT,
                    blocksize=CHUNK_SIZE,
                    callback=self._mic_callback,  # même callback que le micro
                ):
                    while self._running:
                        sd.sleep(100)
                return
            except Exception as exc:
                print(f"[Audio/Loopback] LOOPBACK_DEVICE échoue : {exc}")

        print(
            "[Audio/Loopback] Aucun périphérique loopback disponible. "
            "Seul le micro sera envoyé à Gemini.\n"
            "  → Windows : vérifiez que soundcard est installé.\n"
            "  → Linux   : export LOOPBACK_DEVICE=<nom_source_monitor>\n"
            "  → macOS   : installez BlackHole et export LOOPBACK_DEVICE=<nom>"
        )

    # ------------------------------------------------------------------
    # API publique
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Démarre les threads de capture micro et loopback."""
        self._running = True
        mic_thread = threading.Thread(
            target=self._capture_mic, name="mic-capture", daemon=True
        )
        loopback_thread = threading.Thread(
            target=self._capture_loopback, name="loopback-capture", daemon=True
        )
        self._threads = [mic_thread, loopback_thread]
        for t in self._threads:
            t.start()
        print("[Audio] Capture démarrée (micro + loopback).")

    def stop(self) -> None:
        """Signale l'arrêt à tous les threads de capture."""
        self._running = False
        print("[Audio] Capture arrêtée.")
