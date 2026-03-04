"""
config.py – Configuration statique de l'assistant d'entretien.

Seuls les paramètres qui ne changent pas d'une exécution à l'autre
(modèle, audio, UI) restent ici.  La clé API, le prompt système et le CV
sont gérés dynamiquement via ``settings.py``.
"""

# ---------------------------------------------------------------------------
# Gemini API
# ---------------------------------------------------------------------------

# Modèle Gemini utilisé (doit supporter la modalité audio en temps réel)
GEMINI_MODEL: str = "models/gemini-2.0-flash-live-001"

# Template d'URI WebSocket – la clé API est injectée au moment de la connexion
GEMINI_WS_URI_TEMPLATE: str = (
    "wss://generativelanguage.googleapis.com/ws/"
    "google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent"
    "?key={api_key}"
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
