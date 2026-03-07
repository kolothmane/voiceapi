

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
    "Tu es un recruteur expérimenté et bienveillant qui conduit un entretien oral "
    "de simulation avec le candidat. Pose des questions une par une, adapte-toi au "
    "profil et au poste visé, puis donne un feedback court et concret en fin "
    "d'entretien."
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
        "job_title": "",
        "job_description": "",
        "application_type": "Emploi (CDI/CDD)",
        "interview_duration_minutes": 20,
        "input_device": "",
        "output_device": "",
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
    job_title: str = (settings.get("job_title") or "").strip()
    job_description: str = (settings.get("job_description") or "").strip()
    application_type: str = (settings.get("application_type") or "").strip()
    cv_text: str = (settings.get("cv_text") or "").strip()
    interview_duration_minutes = int(settings.get("interview_duration_minutes") or 20)

    context_lines: list[str] = [
        "=== CONTEXTE CANDIDAT ===",
        f"Type de candidature : {application_type or 'Non précisé'}",
        f"Poste ciblé : {job_title or 'Non précisé'}",
        f"Durée cible de l'entretien : {interview_duration_minutes} minutes",
    ]

    if job_description:
        context_lines.extend(
            [
                "Description du poste :",
                job_description,
            ]
        )

    if cv_text:
        context_lines.extend(
            [
                "CV du candidat :",
                cv_text,
            ]
        )

    context_lines.extend(
        [
            "=== CONSIGNES D'ENTRETIEN ===",
            "- Tu joues le rôle de l'employeur / recruteur.",
            "- Tu mènes une simulation réaliste d'entretien d'embauche.",
            "- Tu poses une seule question à la fois et attends la réponse du candidat.",
            "- Tu ajustes la difficulté selon les réponses et le niveau perçu.",
            "- À la fin, fournis un compte rendu structuré en français: résumé, points forts, axes d'amélioration, conseils concrets.",
        ]
    )

    prompt += "\n\n" + "\n".join(context_lines)
    return prompt
