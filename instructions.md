# Contexte et Rôle
Tu es un développeur Python expert, spécialisé dans la programmation asynchrone (`asyncio`), la manipulation de flux audio en temps réel, et la création d'interfaces graphiques (GUI) de bureau furtives. 

Je veux que tu m'écrives le code et l'architecture complète pour créer un assistant d'entretien en temps réel (type Parakeet AI) sous forme d'application de bureau native. L'application doit écouter l'audio de mon ordinateur et mon micro, envoyer ces données à l'API Gemini Live, et afficher les réponses dans une fenêtre superposée.

# Spécifications Techniques

## 1. Stack Technique Requise
* **Langage :** Python 3.10+
* **Interface Graphique :** `PyQt6` (ou `CustomTkinter` si tu estimes que c'est plus léger pour gérer l'asynchrone). La fenêtre doit être "frameless" (sans bordures), semi-transparente, "Always on Top" (toujours au premier plan), et déplaçable à la souris.
* **Capture Audio :** `sounddevice` pour le microphone, et `soundcard` (ou équivalent natif comme WASAPI sur Windows) pour le loopback (capturer le son des haut-parleurs/de la visio).
* **Communication IA :** `websockets` et `asyncio` pour se connecter à l'API Gemini Multimodal Live (`wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1alpha.GenerativeService.BidiGenerateContent`).

## 2. Fonctionnalités Cibles
1. **Moteur Audio Asynchrone :** Un module capable de capturer simultanément mon microphone et le son sortant de mon PC (le recruteur), de les mixer ou de les envoyer en flux continu (PCM 16-bit, 16kHz ou 24kHz) encodé en base64 vers Gemini.
2. **Gestion WebSockets :** Un client WebSocket robuste qui maintient la connexion ouverte, gère l'envoi des chunks audio, et écoute les réponses texte de Gemini en streaming.
3. **Configuration du Prompt Système :** Lors du setup initial de la connexion WebSocket, l'application doit envoyer un contexte strict à Gemini : *"Tu es un assistant furtif. Ton rôle est d'écouter la conversation et de me souffler des réponses courtes, percutantes et techniques. L'entretien concerne une recherche de stage de 6 mois à partir d'avril 2026, dans le domaine de l'analyse de données avec un focus marketing. Sois direct, pas de phrases d'introduction."*
4. **Mise à jour de l'UI :** Le texte reçu de Gemini doit s'afficher de manière fluide dans la fenêtre flottante, sans bloquer le thread principal de l'interface graphique.

## 3. Contraintes de Développement
* **Pas de code bloquant :** L'UI ne doit jamais geler pendant la capture audio ou l'attente réseau. Sépare bien l'event loop d'asyncio du main thread de l'UI (utilise par exemple `qasync` si tu choisis PyQt, ou gère des threads séparés).
* **Code modulaire :** Divise ta réponse avec des blocs de code clairs pour : 
  1. La configuration de l'API et des WebSockets.
  2. La gestion des flux audio.
  3. L'interface graphique.
  4. Le script principal (`main.py`) qui lie le tout.

# Ce que j'attends de toi maintenant :
Fournis-moi l'architecture complète du projet (noms des fichiers) et écris le code détaillé pour chaque module en respectant scrupuleusement les spécifications ci-dessus. Ajoute des commentaires dans le code pour expliquer comment configurer la capture audio système (loopback), car c'est la partie la plus complexe.
