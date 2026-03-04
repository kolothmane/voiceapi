"""
settings.py – Persistance des paramètres utilisateur.

Les paramètres (clé API, texte du CV, prompt système) sont stockés dans un
fichier JSON dans le répertoire personnel de l'utilisateur afin que
l'application reste portable et puisse être distribuée sans configuration
manuelle des variables d'environnement.

Fichier de configuration : ~/.voiceapi/settings.json
"""

import json
import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Chemins
# ---------------------------------------------------------------------------

SETTINGS_DIR: Path = Path.home() / ".voiceapi"
SETTINGS_FILE: Path = SETTINGS_DIR / "settings.json"

# ---------------------------------------------------------------------------
# Prompt système par défaut
# ---------------------------------------------------------------------------

DEFAULT_SYSTEM_PROMPT: str = (
    "Tu es un assistant furtif. Ton rôle est d'écouter la conversation et de me "
    "souffler des réponses courtes, percutantes et techniques. L'entretien concerne "
    "une recherche de stage de 6 mois à partir d'avril 2026, dans le domaine de "
    "l'analyse de données avec un focus marketing. Sois direct, pas de phrases "
    "d'introduction."
)


# ---------------------------------------------------------------------------
# Chargement / sauvegarde
# ---------------------------------------------------------------------------


def load_settings() -> dict:
    """
    Charge les paramètres depuis ``~/.voiceapi/settings.json``.

    Si le fichier n'existe pas encore, renvoie des valeurs par défaut.
    La variable d'environnement ``GEMINI_API_KEY`` a priorité sur la clé
    sauvegardée (permet un override en CI/CD ou en ligne de commande).
    """
    defaults: dict = {
        "api_key": "",
        "cv_text": "",
        "cv_path": "",
        "system_prompt": DEFAULT_SYSTEM_PROMPT,
    }
    if SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as fh:
                saved = json.load(fh)
            defaults.update(saved)
        except (json.JSONDecodeError, OSError, ValueError) as exc:
            print(f"[Settings] Impossible de lire {SETTINGS_FILE} : {exc}. Valeurs par défaut utilisées.")

    # La variable d'environnement prend toujours le dessus
    env_key = os.environ.get("GEMINI_API_KEY", "")
    if env_key and env_key != "YOUR_API_KEY_HERE":
        defaults["api_key"] = env_key

    return defaults


def save_settings(settings: dict) -> None:
    """
    Sauvegarde les paramètres dans ``~/.voiceapi/settings.json``.

    Crée le répertoire si nécessaire.
    """
    SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    with open(SETTINGS_FILE, "w", encoding="utf-8") as fh:
        json.dump(settings, fh, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Extraction du texte d'un CV
# ---------------------------------------------------------------------------


def extract_cv_text(file_path: str) -> str:
    """
    Extrait le contenu textuel d'un fichier CV.

    Formats supportés :
    * ``.txt``  – lecture directe UTF-8.
    * ``.pdf``  – extraction via ``pypdf`` (doit être installé).
    * Autres    – tentative de lecture comme texte brut.

    Renvoie une chaîne vide si le fichier est inaccessible.
    """
    path = Path(file_path)
    if not path.exists():
        return ""

    suffix = path.suffix.lower()

    if suffix == ".pdf":
        try:
            from pypdf import PdfReader  # noqa: PLC0415

            reader = PdfReader(str(path))
            pages = [page.extract_text() or "" for page in reader.pages]
            return "\n".join(pages).strip()
        except ImportError:
            return "[pypdf non installé – impossible de lire le PDF]"
        except Exception as exc:
            return f"[Erreur lecture PDF : {exc}]"

    # .txt et autres formats : lecture directe
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Construction du prompt système final
# ---------------------------------------------------------------------------


def build_full_system_prompt(settings: dict) -> str:
    """
    Construit le prompt système envoyé à Gemini.

    Si un CV est présent, son contenu est annexé au prompt de base
    pour personnaliser les réponses de Gemini.
    """
    prompt: str = settings.get("system_prompt", DEFAULT_SYSTEM_PROMPT)
    cv_text: str = (settings.get("cv_text") or "").strip()
    if cv_text:
        prompt += f"\n\n=== MON CV ===\n{cv_text}\n==============="
    return prompt
