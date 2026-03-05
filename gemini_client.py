"""
gemini_client.py – Client WebSocket pour l'API Gemini Multimodal Live.

Protocole (v1alpha BidiGenerateContent)
----------------------------------------
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
     le texte depuis ``outputTranscription.text`` (transcription de l'audio
     généré) ainsi que depuis ``modelTurn.parts[].text`` si présent.

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
        Prompt système envoyé lors du setup initial.  Peut inclure le texte
        du CV de l'utilisateur pour personnaliser les réponses.
    """

    def __init__(
        self,
        audio_queue: "asyncio.Queue[str]",
        text_callback,
        api_key: str,
        system_prompt: str = "",
    ) -> None:
        self._audio_queue = audio_queue
        self._text_callback = text_callback
        self._api_key = api_key
        self._system_prompt = system_prompt
        self._ws = None

    @property
    def _ws_uri(self) -> str:
        """URI WebSocket construite dynamiquement depuis la clé API."""
        return GEMINI_WS_URI_TEMPLATE.format(api_key=self._api_key)

    # ------------------------------------------------------------------
    # Initialisation de la session Gemini
    # ------------------------------------------------------------------

    async def _send_setup(self) -> None:
        """Envoie la configuration initiale et attend setupComplete."""
        setup_msg = {
            "setup": {
                "model": GEMINI_MODEL,
                "generation_config": {
                    # Les modèles native-audio (gemini-2.5-flash-native-audio-*)
                    # n'acceptent que AUDIO comme modalité de réponse.
                    # Inclure TEXT dans response_modalities provoque une erreur
                    # 1007 « Request contains an invalid argument ».
                    "response_modalities": ["AUDIO"],
                },
                "system_instruction": {
                    "parts": [{"text": self._system_prompt}]
                },
            }
        }
        await self._ws.send(json.dumps(setup_msg))

        # Attente de setupComplete avec un délai maximal de 10 s.
        # On ignore les frames non-JSON et les messages non pertinents.
        deadline = asyncio.get_running_loop().time() + 10
        while True:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise RuntimeError(
                    "[Gemini] Timeout : setupComplete non reçu en 10 s."
                )
            try:
                raw = await asyncio.wait_for(self._ws.recv(), timeout=remaining)
            except asyncio.TimeoutError:
                raise RuntimeError(
                    "[Gemini] Timeout : setupComplete non reçu en 10 s."
                )
            try:
                data = json.loads(raw)
            except (json.JSONDecodeError, TypeError, ValueError):
                continue  # frame non-JSON → on ignore
            if "setupComplete" in data:
                print("[Gemini] Session configurée avec succès.")
                return
            # Message JSON non pertinent (ex. serverContent précoce) → on ignore

    # ------------------------------------------------------------------
    # Boucle d'envoi audio
    # ------------------------------------------------------------------

    async def _send_audio_loop(self) -> None:
        """Dépile les chunks audio de la queue et les envoie à Gemini."""
        while True:
            b64_chunk: str = await self._audio_queue.get()
            msg = {
                "realtimeInput": {
                    # Format attendu par BidiGenerateContent : tableau de blobs
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
        async for raw in self._ws:
            try:
                data = json.loads(raw)
            except (json.JSONDecodeError, TypeError, ValueError):
                # JSONDecodeError : message non-JSON (ex. frame de contrôle)
                # TypeError / ValueError : frame binaire ou encodage inattendu
                continue

            server_content = data.get("serverContent", {})

            # --- Source 1 : modelTurn → parts[].text ---
            # Présent quand TEXT figure dans responseModalities (modèles non
            # native-audio) ou si le modèle renvoie du texte inline.
            model_turn = server_content.get("modelTurn", {})
            parts = model_turn.get("parts", [])

            for part in parts:
                text: str = part.get("text", "")
                if text:
                    if asyncio.iscoroutinefunction(self._text_callback):
                        await self._text_callback(text)
                    else:
                        self._text_callback(text)

            # --- Source 2 : outputTranscription.text ---
            # Transcription textuelle de l'audio généré par les modèles
            # native-audio (si fournie par l'API sur ce modèle/version).
            output_transcription = server_content.get("outputTranscription", {})
            transcript: str = output_transcription.get("text", "")
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
        async with websockets.connect(
            self._ws_uri,
            # Les pings WebSocket (protocole niveau transport) ne sont pas
            # supportés par Gemini Live – on les désactive pour éviter des
            # déconnexions intempestives.
            ping_interval=None,
            # Limite supérieure de la taille des messages WebSocket (100 MB)
            max_size=100 * 1024 * 1024,
        ) as ws:
            self._ws = ws
            await self._send_setup()

            # Les deux boucles tournent en parallèle ; si l'une s'arrête,
            # l'autre est annulée proprement.
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
