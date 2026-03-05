"""
gemini_client.py – Client WebSocket pour l'API Gemini Multimodal Live.

Protocole (v1alpha BidiGenerateContent)
---------------------------------------
1. Connexion WebSocket sur l'URI construite depuis la clé API fournie.
   Les modèles native-audio requièrent le endpoint v1alpha.
2. Envoi d'un message ``setup`` contenant :
   - le modèle utilisé,
   - la modalité de réponse AUDIO (seule valeur valide pour les modèles
     native-audio ; TEXT dans responseModalities est rejeté avec 1007),
   - le prompt système (instruction stricte), enrichi du CV si fourni.
3. Attente du message ``setupComplete`` du serveur.
4. En parallèle :
   - Boucle d'envoi  : dépile les chunks base64 de la queue audio et les
     envoie via ``realtimeInput.mediaChunks``.
   - Boucle de réception : lit les messages ``serverContent`` et extrait
     le texte depuis ``modelTurn.parts[].text`` si présent.

Référence : https://ai.google.dev/api/multimodal-live
"""

import asyncio
import json

import websockets
import websockets.exceptions

from config import GEMINI_MODEL, GEMINI_WS_URI_TEMPLATE, SAMPLE_RATE


class GeminiClient:
    """
    Maintient une connexion WebSocket persistante avec Gemini Live et
    stream les chunks audio de la queue vers l'API.

    Parameters
    ----------
    audio_queue:
        Queue asyncio qui fournit des chaînes base64 (PCM 16-bit, 16 kHz).
    text_callback:
        Fonction (ou coroutine) appelée avec chaque morceau de texte reçu.
        Signature : ``callback(text: str) -> None`` (ou coroutine équivalente).
    api_key:
        Clé API Gemini utilisée pour construire l'URI WebSocket.
    system_prompt:
        Prompt système envoyé lors du setup initial. Peut inclure le texte
        du CV de l'utilisateur pour personnaliser les réponses.
    connected_callback:
        Fonction (ou coroutine) appelée quand la session est configurée
        (après réception de setupComplete).
    """

    def __init__(
        self,
        audio_queue: "asyncio.Queue[str]",
        text_callback,
        api_key: str,
        system_prompt: str = "",
        connected_callback=None,
    ) -> None:
        self._audio_queue = audio_queue
        self._text_callback = text_callback
        self._api_key = api_key
        self._system_prompt = system_prompt
        self._connected_callback = connected_callback
        self._ws: websockets.WebSocketClientProtocol | None = None

    @property
    def _ws_uri(self) -> str:
        """URI WebSocket construite dynamiquement depuis la clé API."""
        return GEMINI_WS_URI_TEMPLATE.format(api_key=self._api_key)

    # ------------------------------------------------------------------
    # Initialisation de la session Gemini
    # ------------------------------------------------------------------

    def _build_setup_messages(self) -> list[dict]:
        """Construit le message de setup pour l'API Gemini Live."""
        setup = {
            "setup": {
                "model": GEMINI_MODEL,
                "generationConfig": {
                    "responseModalities": ["AUDIO"],
                },
                "systemInstruction": {"parts": [{"text": self._system_prompt}]},
            }
        }
        return [setup]

    async def _send_setup(self, setup_msg: dict) -> None:
        """Envoie une configuration initiale et attend setupComplete."""
        if not self._ws:
            raise RuntimeError("[Gemini] WebSocket non initialisé.")

        await self._ws.send(json.dumps(setup_msg))

        deadline = asyncio.get_running_loop().time() + 10
        while True:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise RuntimeError("[Gemini] Timeout : setupComplete non reçu en 10 s.")

            try:
                raw = await asyncio.wait_for(self._ws.recv(), timeout=remaining)
            except asyncio.TimeoutError as exc:
                raise RuntimeError("[Gemini] Timeout : setupComplete non reçu en 10 s.") from exc

            try:
                data = json.loads(raw)
            except (json.JSONDecodeError, TypeError, ValueError):
                continue

            if "setupComplete" in data:
                print("[Gemini] Session configurée avec succès.")
                if self._connected_callback:
                    if asyncio.iscoroutinefunction(self._connected_callback):
                        await self._connected_callback()
                    else:
                        self._connected_callback()
                return

            # Renvoie l'erreur serveur de façon explicite au lieu de boucler.
            if data.get("error"):
                raise RuntimeError(f"[Gemini] Setup rejeté : {data['error']}")

    # ------------------------------------------------------------------
    # Boucle d'envoi audio
    # ------------------------------------------------------------------

    async def _send_audio_loop(self) -> None:
        """Dépile les chunks audio de la queue et les envoie à Gemini."""
        if not self._ws:
            raise RuntimeError("[Gemini] WebSocket non initialisé.")

        while True:
            b64_chunk: str = await self._audio_queue.get()
            msg = {
                "realtimeInput": {
                    "mediaChunks": [
                        {
                            "mimeType": f"audio/pcm;rate={SAMPLE_RATE}",
                            "data": b64_chunk,
                        }
                    ]
                }
            }
            try:
                await self._ws.send(json.dumps(msg))
            except websockets.exceptions.ConnectionClosed:
                print("[Gemini] Connexion fermée pendant l'envoi audio.")
                break

    # ------------------------------------------------------------------
    # Boucle de réception des réponses
    # ------------------------------------------------------------------

    async def _receive_loop(self) -> None:
        """Écoute les messages serveur et extrait les fragments de texte."""
        if not self._ws:
            raise RuntimeError("[Gemini] WebSocket non initialisé.")

        async for raw in self._ws:
            try:
                data = json.loads(raw)
            except (json.JSONDecodeError, TypeError, ValueError):
                continue

            server_content = data.get("serverContent", {})

            # --- Source 1 : modelTurn → parts[].text ---
            model_turn = server_content.get("modelTurn", {})
            parts = model_turn.get("parts", []) or []
            for part in parts:
                text: str = part.get("text", "") or ""
                if text:
                    if asyncio.iscoroutinefunction(self._text_callback):
                        await self._text_callback(text)
                    else:
                        self._text_callback(text)

            # --- Source 2 : outputTranscription.text ---
            output_transcription = server_content.get("outputTranscription", {})
            transcript: str = output_transcription.get("text", "") or ""
            if transcript:
                if asyncio.iscoroutinefunction(self._text_callback):
                    await self._text_callback(transcript)
                else:
                    self._text_callback(transcript)

    # ------------------------------------------------------------------
    # Point d'entrée public
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """Connecte, configure la session, puis lance les deux boucles."""
        print(f"[Gemini] Connexion à {self._ws_uri[:60]}…")

        setup_errors: list[str] = []
        setup_messages = self._build_setup_messages()

        for setup_msg in setup_messages:
            try:
                async with websockets.connect(
                    self._ws_uri,
                    # Gemini Live: désactiver les pings WS pour éviter des déconnexions.
                    ping_interval=None,
                    # Limite supérieure de la taille des messages WebSocket (100 MB)
                    max_size=100 * 1024 * 1024,
                ) as ws:
                    self._ws = ws
                    await self._send_setup(setup_msg)

                    done, pending = await asyncio.wait(
                        [
                            asyncio.create_task(self._send_audio_loop()),
                            asyncio.create_task(self._receive_loop()),
                        ],
                        return_when=asyncio.FIRST_COMPLETED,
                    )

                    for task in pending:
                        task.cancel()

                    # Propage les éventuelles exceptions
                    for task in done:
                        task.result()

                    return

            except Exception as exc:
                setup_errors.append(str(exc))
                print(f"[Gemini] Variante setup échouée : {exc}")

        raise RuntimeError(" | ".join(setup_errors) or "[Gemini] Échec de setup")