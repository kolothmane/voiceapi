# Fonctionnement détaillé de l'application `voiceapi`

Ce document explique **comment l’application fonctionne de bout en bout** : démarrage, capture audio, communication avec Gemini Live, mise à jour de l’interface, et gestion des erreurs/reconnexions.

---

## 1) Objectif de l’application

L’application est un assistant desktop temps réel qui :

1. capte l’audio du **microphone**,
2. tente de capter aussi le **son système (loopback)**,
3. envoie ces chunks audio en continu à **Gemini Live** via WebSocket,
4. affiche les retours textuels dans une **fenêtre overlay** PyQt6.

---

## 2) Architecture globale

Les modules principaux :

- `main.py` : point d’entrée, orchestration asyncio + Qt (via qasync), gestion session.
- `audio_engine.py` : capture micro + loopback, encodage base64, push vers queue asyncio.
- `gemini_client.py` : connexion WebSocket Gemini, setup session, envoi audio, réception texte.
- `ui.py` : fenêtre overlay, signaux Qt (TextBridge), affichage statut/texte.
- `settings.py` : chargement/sauvegarde clé API, prompt, CV.
- `config.py` : constantes (modèle, sample rate, taille chunks, dimensions UI, etc.).

Flux principal :

```text
AudioEngine (threads) -> asyncio.Queue[str] -> GeminiClient (WebSocket)
                                                -> callback texte -> TextBridge (Qt signal)
                                                -> OverlayWindow (affichage)
```

---

## 3) Démarrage de l’application (`main.py`)

### Étapes de boot

1. Chargement des paramètres (`load_settings`).
2. Initialisation Qt (`QApplication`).
3. Ouverture du dialogue de configuration si clé API absente.
4. Création de la fenêtre overlay + bridge de signaux.
5. Installation de la boucle `qasync.QEventLoop` (fusion Qt + asyncio).
6. Lancement de la coroutine principale `async_main(...)`.

### Session asynchrone (`async_main`)

- Crée une `asyncio.Queue` bornée (anti-accumulation infinie).
- Démarre `AudioEngine.start()` (capture en threads).
- Construit le prompt système final (prompt + CV).
- Crée `GeminiClient` avec callback texte et callback “connecté”.
- Entre dans une boucle de reconnexion :
  - tente `client.run()` ;
  - en cas d’erreur : affiche message, vide la queue, attend avec backoff exponentiel.

---

## 4) Capture audio (`audio_engine.py`)

## 4.1 Microphone

- Capture via `sounddevice.InputStream`.
- Callback `_mic_callback` exécuté à chaque bloc :
  - downmix en mono si entrée multi-canaux,
  - conversion PCM int16,
  - encodage base64,
  - enqueue thread-safe vers la boucle asyncio.

## 4.2 Injection thread-safe dans asyncio

Comme la capture tourne dans des threads natifs et non dans la loop principale :

- on utilise `loop.call_soon_threadsafe(...)` pour planifier l’insertion queue,
- la lambda capture la valeur courante (`lambda e=encoded: ...`) pour éviter les bugs de fermeture (late binding).

## 4.3 Loopback système

### Stratégie en cascade

1. **Tentative 1 (Windows prioritaire)** : `soundcard` WASAPI loopback.
2. **Tentative 2 (fallback Windows)** : `sounddevice` + `WasapiSettings(loopback=True)` sur périphériques WASAPI (sortie par défaut puis autres candidats).
3. **Tentative 3 (Linux/macOS)** : `LOOPBACK_DEVICE` via `sounddevice.InputStream`.

Si tout échoue, l’application continue en mode **micro uniquement**.

---

## 5) Client Gemini Live (`gemini_client.py`)

## 5.1 Connexion

- Connexion WebSocket à l’URI construite avec la clé API (`GEMINI_WS_URI_TEMPLATE`).
- `ping_interval=None` pour éviter des incompatibilités avec le service Live.
- `max_size` élevé pour supporter des frames volumineuses.

## 5.2 Setup session

- Construction du message setup avec :
  - `model`,
  - `generationConfig.responseModalities = ["AUDIO"]`,
  - `systemInstruction.parts[].text`.
- Envoi setup puis attente explicite de `setupComplete` (timeout 10s).
- Si frame d’erreur serveur reçue, exception explicite.

## 5.3 Envoi audio

- Boucle infinie `_send_audio_loop` :
  - lit base64 depuis la queue,
  - envoie `realtimeInput.mediaChunks` (mime type audio PCM + rate).

## 5.4 Réception texte

- Boucle `_receive_loop` : parse JSON, ignore frames invalides/non pertinentes.
- Extrait le texte depuis :
  - `serverContent.modelTurn.parts[].text`,
  - `serverContent.outputTranscription.text` (si fourni).
- Appelle le callback texte pour mise à jour UI.

---

## 6) Interface utilisateur

L’UI repose sur des signaux Qt (bridge) pour **ne pas bloquer** le thread principal :

- `text_received` : ajoute du texte dans l’overlay.
- `status_changed` : met à jour l’état (connexion/reconnexion/connecté).
- `restart_requested` : annule la session courante et redémarre une nouvelle session avec les nouveaux paramètres.

La fenêtre reste légère : affichage de texte, statut, et actions de configuration.

---

## 7) Gestion des erreurs & résilience

Mécanismes présents :

- Timeout sur `setupComplete`.
- Gestion des fermetures WebSocket durant l’envoi audio.
- Reconnexion automatique avec backoff exponentiel côté `main.py`.
- Vidage de queue en mode erreur pour éviter d’envoyer de l’audio périmé après reconnexion.
- Fallbacks multi-niveaux pour loopback audio.

---

## 8) Points d’attention opérationnels

- Si le loopback échoue mais le micro fonctionne, l’app reste utilisable partiellement.
- Si le statut reste sur connexion longtemps, vérifier clé API, réseau, et messages d’erreur setup.
- Sur Windows, un conflit version `soundcard`/NumPy peut empêcher la voie `soundcard`; le fallback `sounddevice` prend alors le relais.

---

## 9) Résumé ultra-court

- **Capture audio** (micro + loopback si possible) -> **queue asyncio** -> **Gemini WebSocket** -> **texte reçu** -> **overlay Qt**.
- Le tout est non bloquant grâce à **threads audio + qasync**.
- En cas de panne : **reconnexion auto** + **fallbacks audio**.

