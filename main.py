"""
main.py – Point d'entrée de l'assistant d'entretien en temps réel.

Rôle de ce fichier
------------------
* Charge les paramètres utilisateur (clé API, CV, prompt) via ``settings.py``.
* Affiche la boîte de dialogue de configuration au premier lancement
  (ou si aucune clé API n'est configurée).
* Initialise l'application Qt.
* Crée la fenêtre overlay et le bridge asyncio↔Qt.
* Configure ``qasync`` pour que la boucle asyncio tourne dans le même
  thread que Qt (pas de multithreading OS supplémentaire nécessaire).
* Lance les deux tâches asyncio :
    1. ``audio_engine.start()`` – capture micro + loopback.
    2. ``gemini_client.run()`` – WebSocket vers Gemini Live.
* Gère le signal ``restart_requested`` pour relancer la connexion Gemini
  lorsque l'utilisateur modifie ses paramètres en cours de session.

Séparation des responsabilités
--------------------------------
Qt (thread principal)  ←→  TextBridge (signaux)  ←→  asyncio (qasync)
        ↑                                                     ↓
   OverlayWindow                                     GeminiClient
   SettingsDialog                                    AudioEngine (threads)
"""

import asyncio
import sys

import qasync
from PyQt6.QtWidgets import QApplication, QDialog

from audio_engine import AudioEngine
from gemini_client import GeminiClient
from settings import build_full_system_prompt, load_settings, save_settings
from ui import OverlayWindow, SettingsDialog, TextBridge


async def async_main(bridge: TextBridge, settings: dict) -> None:
    """
    Cœur asynchrone de l'application.

    1. Crée la queue audio partagée.
    2. Démarre la capture audio (threads dédiés).
    3. Lance le client Gemini WebSocket avec la clé API et le prompt
       (enrichi du CV si présent).
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

    # --- Prompt système final (prompt personnalisé + CV si présent) ---
    system_prompt = build_full_system_prompt(settings)

    # --- Client Gemini ---
    client = GeminiClient(
        audio_queue=audio_queue,
        text_callback=on_text,
        api_key=settings.get("api_key", ""),
        system_prompt=system_prompt,
    )

    try:
        await client.run()
    except asyncio.CancelledError:
        # Annulation intentionnelle lors d'un changement de paramètres en cours de session
        print("[Main] Session annulée pour rechargement des paramètres.")
    except Exception as exc:
        error_msg = f"\n\n⚠️  Erreur Gemini : {exc}"
        bridge.text_received.emit(error_msg)
        bridge.status_changed.emit("🔴 Déconnecté")
        print(f"[Main] {error_msg}")
    finally:
        engine.stop()


def main() -> None:
    # --- Chargement des paramètres (fichier JSON + variable d'environnement) ---
    settings = load_settings()

    # --- Application Qt ---
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)

    # --- Boîte de dialogue de configuration si aucune clé API ---
    if not settings.get("api_key"):
        dialog = SettingsDialog(settings)
        result = dialog.exec()
        if result == QDialog.DialogCode.Accepted:
            settings = dialog.get_settings()
            save_settings(settings)
        else:
            # L'utilisateur a annulé → on quitte proprement
            sys.exit(0)

    # --- Bridge asyncio ↔ Qt ---
    bridge = TextBridge()

    # --- Fenêtre overlay ---
    window = OverlayWindow(bridge=bridge, settings=settings)
    window.show()

    # --- Boucle d'événements qasync (asyncio + Qt dans le même thread) ---
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)

    # Liste d'un élément utilisée comme conteneur mutable capturé par la closure
    # _restart_session. Python 3.10 ne permet pas 'nonlocal' sur une variable
    # définie après le 'with loop:' qui n'est pas encore en portée ici.
    current_task: list = [None]

    def _restart_session(new_settings: dict) -> None:
        """Annule la connexion courante et en démarre une nouvelle."""
        task = current_task[0]
        if task is not None and not task.done():
            task.cancel()
        current_task[0] = loop.create_task(async_main(bridge, new_settings))

    bridge.restart_requested.connect(_restart_session)

    with loop:
        # Planifie la tâche principale asyncio
        current_task[0] = loop.create_task(async_main(bridge, settings))
        # Démarre la boucle combinée Qt + asyncio
        loop.run_forever()


if __name__ == "__main__":
    main()
