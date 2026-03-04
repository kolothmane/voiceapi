"""
config.py – Configuration centrale de l'assistant d'entretien.

Toutes les constantes, clés API, et paramètres audio/UI sont regroupées ici
pour faciliter la personnalisation sans toucher au reste du code.
"""

import os

# ---------------------------------------------------------------------------
# Gemini API
# ---------------------------------------------------------------------------

# Récupère la clé dans la variable d'environnement GEMINI_API_KEY.
# Sur Windows : set GEMINI_API_KEY=AIza...
# Sur Linux/macOS : export GEMINI_API_KEY=AIza...
GEMINI_API_KEY: str = os.environ.get("GEMINI_API_KEY", "YOUR_API_KEY_HERE")

# URI WebSocket de l'API Gemini Multimodal Live (v1alpha)
GEMINI_WS_URI: str = (
    "wss://generativelanguage.googleapis.com/ws/"
    "google.ai.generativelanguage.v1alpha.GenerativeService.BidiGenerateContent"
    f"?key={GEMINI_API_KEY}"
)

# Modèle Gemini utilisé (doit supporter la modalité audio en temps réel)
GEMINI_MODEL: str = "models/gemini-2.0-flash-live-001"

# ---------------------------------------------------------------------------
# Prompt système envoyé à Gemini à la connexion
# ---------------------------------------------------------------------------
SYSTEM_PROMPT: str = (
    "Tu es un assistant furtif. Ton rôle est d'écouter la conversation et de me "
    "souffler des réponses courtes, percutantes et techniques. L'entretien concerne "
    "une recherche de stage de 6 mois à partir d'avril 2026, dans le domaine de "
    "l'analyse de données avec un focus marketing. Sois direct, pas de phrases "
    "d'introduction."
)

# ---------------------------------------------------------------------------
# Paramètres audio
# ---------------------------------------------------------------------------

# Fréquence d'échantillonnage en Hz. Gemini Live accepte 16000 ou 24000.
SAMPLE_RATE: int = 16000

# Nombre de canaux (1 = mono). Gemini attend du mono.
CHANNELS: int = 1

# Nombre de frames par bloc audio envoyé au callback sounddevice.
CHUNK_SIZE: int = 1024

# Format PCM (sounddevice attend 'int16' pour de la compatibilité maximale)
AUDIO_FORMAT: str = "int16"

# ---------------------------------------------------------------------------
# Interface graphique
# ---------------------------------------------------------------------------

WINDOW_WIDTH: int = 480
WINDOW_HEIGHT: int = 320

# Opacité globale de la fenêtre (0.0 = invisible, 1.0 = opaque)
WINDOW_OPACITY: float = 0.88

# Taille de la police du texte Gemini
FONT_SIZE: int = 13
