## Instructions Copilot

Ceci est un fichier où tu vas trouver des instructions que tu vas devoir respecter à chaque fois.
Quand tu commences à modifier les fichiers, lis ce markdown pour avoir une idée sur les modifications qui ont déjà eu lieu dans le passé.
Quand tu finis tes modifications, rajoute une section dans ce fichier où tu expliques les modifications que tu as faites.

---

## Historique des modifications

### Fix : Queue audio pleine – chunks abandonnés en boucle (mars 2025)

**Problème** : Au lancement, la capture audio (micro + loopback) démarrait
immédiatement et remplissait la queue (300 chunks ≈ 19 s) *avant* que la
session Gemini ne soit prête. La boucle d'envoi démarrait avec un backlog
de 300 chunks périmés qu'elle ne parvenait jamais à résorber, ce qui
provoquait des messages « Queue pleine » en continu.

**Corrections apportées** :

| Fichier | Modification |
|---------|-------------|
| `audio_engine.py` | Ajout d'un `threading.Event` (`_gate`) qui bloque l'ajout de chunks dans la queue tant que Gemini n'est pas connecté. Méthodes `enable_sending()` / `disable_sending()` pour piloter la porte. Le compteur `_dropped_chunks` est remis à zéro à chaque ouverture de porte. |
| `gemini_client.py` | Vidage de la queue juste après `_send_setup()` (avant le lancement des boucles d'envoi/réception) pour éliminer les éventuels chunks résiduels. |
| `main.py` | `on_connected` appelle `engine.enable_sending()` ; le handler d'erreur appelle `engine.disable_sending()` avant la tentative de reconnexion. |

### Fix : Erreur 1007 « invalid argument » lors de l'envoi audio (mars 2025)

**Problème** : Après la configuration réussie de la session Gemini, l'envoi
de chunks audio provoquait une erreur 1007 « Request contains an invalid
argument » suivie d'une déconnexion WebSocket en boucle.

**Cause** : Le champ `realtimeInput.mediaChunks` (tableau d'objets) a été
déprécié dans le schéma Live API au profit de `realtimeInput.audio` (objet
unique contenant `mimeType` et `data`).

**Corrections apportées** :

| Fichier | Modification |
|---------|-------------|
| `gemini_client.py` | Remplacement de `realtimeInput.mediaChunks` par `realtimeInput.audio`. Les chunks regroupés (batching) sont concaténés en données PCM brutes puis ré-encodés en un seul blob base64 avant envoi. Ajout de `import base64` pour la concaténation. Mise à jour des commentaires et du docstring du module. |