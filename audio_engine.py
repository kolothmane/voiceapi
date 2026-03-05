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
import threading

import numpy as np
import sounddevice as sd

try:
    import soundcard as sc

    _SOUNDCARD_AVAILABLE = True
except Exception:  # ImportError ou OSError si pas de WASAPI
    _SOUNDCARD_AVAILABLE = False

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
                with loopback_mic.recorder(
                    samplerate=SAMPLE_RATE, channels=CHANNELS
                ) as recorder:
                    print(
                        f"[Audio/Loopback] WASAPI loopback actif sur : {speaker.name}"
                    )
                    while self._running:
                        # recorder.record() retourne un tableau float32 normalisé [-1, 1]
                        data = recorder.record(numframes=CHUNK_SIZE)
                        pcm = (data * 32767).astype(np.int16)
                        encoded = base64.b64encode(pcm.tobytes()).decode("utf-8")
                        self._loop.call_soon_threadsafe(
                            lambda: self._safe_enqueue(encoded)
                        )
                return  # succès → on ne passe pas aux alternatives
            except Exception as exc:
                print(
                    f"[Audio/Loopback] soundcard échoue ({exc}). "
                    "Tentative avec LOOPBACK_DEVICE…"
                )

        # --- Tentative 2 : sounddevice + LOOPBACK_DEVICE (Linux/macOS) ---
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
