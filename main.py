"""
main.py – Point d'entrée de l'assistant d'entretien en temps réel.

Rôle de ce fichier
------------------
* Initialise l'application Qt.
* Crée la fenêtre overlay et le bridge asyncio↔Qt.
* Configure ``qasync`` pour que la boucle asyncio tourne dans le même
  thread que Qt (pas de multithreading OS supplémentaire nécessaire).
* Lance les deux tâches asyncio :
    1. ``audio_engine.start()`` – capture micro + loopback.
    2. ``gemini_client.run()`` – WebSocket vers Gemini Live.

Séparation des responsabilités
--------------------------------
Qt (thread principal)  ←→  TextBridge (signaux)  ←→  asyncio (qasync)
        ↑                                                     ↓
   OverlayWindow                                     GeminiClient
                                                     AudioEngine (threads)
"""

import asyncio
import sys

import qasync
from PyQt6.QtWidgets import QApplication

from audio_engine import AudioEngine
from config import GEMINI_API_KEY
from gemini_client import GeminiClient
from ui import OverlayWindow, TextBridge


async def async_main(bridge: TextBridge) -> None:
    """
    Cœur asynchrone de l'application.

    1. Crée la queue audio partagée.
    2. Démarre la capture audio (threads dédiés).
    3. Lance le client Gemini WebSocket.
    4. En cas d'erreur, affiche le message dans l'overlay.
    """
    bridge.status_changed.emit("⏳ Connexion à Gemini…")

    # Queue FIFO bornée pour éviter une accumulation infinie de chunks
    # si le réseau est plus lent que la capture audio.
    audio_queue: asyncio.Queue[str] = asyncio.Queue(maxsize=300)

    loop = asyncio.get_event_loop()

    # --- Moteur audio ---
    engine = AudioEngine(loop=loop, audio_queue=audio_queue)
    engine.start()

    # --- Callback texte : émettre un signal Qt (thread-safe) ---
    def on_text(text: str) -> None:
        bridge.text_received.emit(text)

    # --- Client Gemini ---
    client = GeminiClient(audio_queue=audio_queue, text_callback=on_text)

    try:
        await client.run()
    except Exception as exc:
        error_msg = f"\n\n⚠️  Erreur Gemini : {exc}"
        bridge.text_received.emit(error_msg)
        bridge.status_changed.emit("🔴 Déconnecté")
        print(f"[Main] {error_msg}")
    finally:
        engine.stop()


def main() -> None:
    # --- Vérification de la clé API avant de démarrer ---
    if GEMINI_API_KEY == "YOUR_API_KEY_HERE":
        print(
            "\n[ERREUR] Clé API Gemini manquante.\n"
            "Définissez la variable d'environnement GEMINI_API_KEY :\n"
            "  Windows  : set GEMINI_API_KEY=AIza...\n"
            "  Linux/Mac: export GEMINI_API_KEY=AIza...\n"
            "Ou modifiez directement config.py (déconseillé).\n"
        )
        # On continue quand même pour afficher la fenêtre (utile pour les tests UI)

    # --- Application Qt ---
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)

    # --- Bridge asyncio ↔ Qt ---
    bridge = TextBridge()

    # --- Fenêtre overlay ---
    window = OverlayWindow(bridge=bridge)
    window.show()

    # --- Boucle d'événements qasync (asyncio + Qt dans le même thread) ---
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)

    with loop:
        # Planifie la tâche principale asyncio
        loop.create_task(async_main(bridge))
        # Démarre la boucle combinée Qt + asyncio
        loop.run_forever()


if __name__ == "__main__":
    main()
