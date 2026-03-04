# 🎙 Interview Assistant – Assistant d'entretien en temps réel

Application de bureau furtive qui écoute votre micro **et** le son de vos haut-parleurs,
envoie ces flux audio à l'**API Gemini Live**, et affiche les réponses dans une fenêtre
flottante semi-transparente, toujours au premier plan.

> **Cas d'usage typique :** entretien de stage ou d'embauche en visio-conférence.
> L'assistant souffle des réponses courtes et techniques en temps réel.

---

## ✨ Fonctionnalités

| Fonctionnalité | Description |
|---|---|
| 🎙 Capture audio | Micro + loopback système (recruteur) en simultané |
| 🤖 Gemini Live | Réponses texte en streaming via WebSocket |
| 📄 Upload de CV | Importez votre CV (PDF ou TXT) pour personnaliser les réponses |
| ✏️ Prompt personnalisé | Modifiez le contexte envoyé à Gemini depuis l'interface |
| ⚙ Interface de configuration | Dialogue graphique au démarrage – pas de ligne de commande requise |
| 💾 Persistance | Les paramètres sont sauvegardés dans `~/.voiceapi/settings.json` |
| 🔄 Reconnexion à chaud | Changez les paramètres en cours de session sans quitter l'application |

---

## 📁 Architecture du projet

```
voiceapi/
├── settings.py        # Persistance des paramètres (clé API, CV, prompt)
├── config.py          # Constantes statiques : modèle Gemini, audio, UI
├── audio_engine.py    # Capture micro + loopback (sounddevice / soundcard)
├── gemini_client.py   # Client WebSocket Gemini Multimodal Live
├── ui.py              # Fenêtre overlay + dialogue de configuration (PyQt6)
├── main.py            # Point d'entrée – lie tous les modules
├── requirements.txt   # Dépendances Python
└── README.md          # Ce fichier
```

---

## ✅ Tutoriel : Rendre le logiciel opérationnel

### Étape 1 – Prérequis système

| Élément | Minimum requis |
|---|---|
| Python | 3.10 ou supérieur |
| Système d'exploitation | Windows 10/11 (recommandé), Linux, macOS |
| Connexion internet | Requise pour l'API Gemini |

Vérifiez votre version de Python :
```bash
python --version   # ou python3 --version
```

---

### Étape 2 – Cloner le dépôt

```bash
git clone https://github.com/kolothmane/voiceapi.git
cd voiceapi
```

---

### Étape 3 – Créer un environnement virtuel (recommandé)

```bash
# Windows
python -m venv .venv
.venv\Scripts\activate

# Linux / macOS
python3 -m venv .venv
source .venv/bin/activate
```

---

### Étape 4 – Installer les dépendances

```bash
pip install -r requirements.txt
```

> **Remarque Windows :** `soundcard` nécessite parfois les
> [Visual C++ Redistributable](https://aka.ms/vs/17/release/vc_redist.x64.exe).
> Si l'installation échoue, essayez :
> ```bash
> pip install soundcard --pre
> ```

> **Remarque Linux :** `sounddevice` et `soundcard` requièrent PortAudio :
> ```bash
> sudo apt install portaudio19-dev python3-dev
> ```

---

### Étape 5 – Lancer l'application

```bash
python main.py
```

**Au premier lancement**, si aucune clé API n'est détectée, la fenêtre de
configuration s'ouvre automatiquement :

```
┌──────────────────────────────────────────────┐
│  ⚙  Configuration – Interview Assistant      │
│                                              │
│  🔑 Clé API Gemini                           │
│  ┌─────────────────────────────────┐  [👁]   │
│  │ AIzaSy...                       │         │
│  └─────────────────────────────────┘         │
│                                              │
│  📄 CV / Resume (optionnel)                  │
│  [📂 Parcourir…]  [✕ Supprimer]             │
│  Aperçu du texte extrait…                    │
│                                              │
│  ✏️ Prompt système          [↺ Réinitialiser] │
│  ┌─────────────────────────────────────────┐ │
│  │ Tu es un assistant furtif…              │ │
│  └─────────────────────────────────────────┘ │
│                                              │
│              [✕ Annuler] [✓ Sauvegarder & Démarrer] │
└──────────────────────────────────────────────┘
```

Remplissez votre clé API, puis cliquez **Sauvegarder & Démarrer**.
Les paramètres sont sauvegardés dans `~/.voiceapi/settings.json` pour
les prochains lancements.

---

### Étape 6 – Configurer la capture du son système (loopback)

La capture loopback permet d'entendre ce que dit le recruteur (son qui sort des haut-parleurs).

#### 🪟 Windows (automatique)

Aucune configuration supplémentaire n'est nécessaire.
`soundcard` utilise automatiquement l'API **WASAPI loopback** de Windows.

#### 🐧 Linux (PulseAudio / PipeWire)

Listez les sources monitor disponibles :
```bash
pactl list short sources | grep monitor
```

Exemple de sortie :
```
alsa_output.pci-0000_00_1f.3.analog-stereo.monitor
```

Exportez le nom de la source monitor :
```bash
export LOOPBACK_DEVICE="alsa_output.pci-0000_00_1f.3.analog-stereo.monitor"
```

#### 🍎 macOS

macOS ne fournit pas de loopback natif.
Installez [BlackHole](https://github.com/ExistentialAudio/BlackHole) (gratuit) :

1. Téléchargez et installez **BlackHole 2ch**.
2. Dans *Paramètres Système → Son → Sortie*, sélectionnez **BlackHole 2ch**.
3. Optionnel : créez un *Aggregate Device* pour entendre le son en même temps.
4. Exportez la variable d'environnement :
   ```bash
   export LOOPBACK_DEVICE="BlackHole 2ch"
   ```

---

### Étape 7 – Utiliser la fenêtre overlay

Une fois démarré, une fenêtre flottante semi-transparente s'affiche.
L'assistant écoute en temps réel et affiche ses suggestions.

**Contrôles de la fenêtre :**

| Bouton / Action | Effet |
|---|---|
| Clic gauche maintenu + glisser | Déplacer la fenêtre |
| ⚙ | Ouvrir les paramètres (clé API, CV, prompt) |
| 🗑 | Effacer le texte affiché |
| ✕ | Fermer l'application |

> **Paramètres en cours de session :** Le bouton ⚙ permet de changer la clé API,
> le CV ou le prompt **sans quitter** l'application. La connexion Gemini est
> automatiquement relancée avec les nouveaux paramètres.

---

## 📄 Upload de CV

Importez votre CV pour que Gemini adapte ses réponses à votre profil
(compétences, expériences, formations).

**Formats supportés :**

| Format | Méthode d'extraction |
|---|---|
| `.txt` | Lecture directe |
| `.pdf` | Extraction via `pypdf` |
| Autres | Tentative de lecture comme texte brut |

Le texte extrait est ajouté automatiquement au prompt système sous la forme :

```
[Votre prompt personnalisé]

=== MON CV ===
[Contenu du CV]
===============
```

---

## ✏️ Prompt système personnalisé

Le prompt système définit le comportement de Gemini pendant la session.
Modifiez-le depuis l'interface ⚙ pour l'adapter à votre secteur, poste ou style.

**Prompt par défaut :**
```
Tu es un assistant furtif. Ton rôle est d'écouter la conversation et de me
souffler des réponses courtes, percutantes et techniques. L'entretien concerne
une recherche de stage de 6 mois à partir d'avril 2026, dans le domaine de
l'analyse de données avec un focus marketing. Sois direct, pas de phrases
d'introduction.
```

Le bouton **↺ Réinitialiser** dans le dialogue de configuration restaure ce prompt.

---

## 💾 Persistance des paramètres

Les paramètres sont stockés dans `~/.voiceapi/settings.json` :

```json
{
  "api_key": "AIzaSy...",
  "cv_path": "/home/user/cv.pdf",
  "cv_text": "Jean Dupont – Étudiant en Master Data...",
  "system_prompt": "Tu es un assistant furtif..."
}
```

> ⚠️ Ce fichier contient votre clé API en clair. Ne le partagez pas et
> ne le committez **jamais** dans un dépôt Git.
> Ajoutez `~/.voiceapi/` ou ce fichier à votre `.gitignore` si nécessaire.

La variable d'environnement `GEMINI_API_KEY`, si définie, prend toujours
le dessus sur la valeur sauvegardée (pratique pour les environnements CI/CD).

---

## 📦 Distribution (envoyer à des amis)

Ce projet est conçu pour être **distribuable** : aucune configuration
en ligne de commande n'est requise. Il suffit de :

1. Partager le dossier du projet (ou une archive ZIP).
2. Le destinataire installe les dépendances :
   ```bash
   pip install -r requirements.txt
   ```
3. Il lance `python main.py` et saisit sa propre clé API dans le dialogue.

### Packaging en exécutable standalone

Pour distribuer sans nécessiter d'installation Python, utilisez **PyInstaller** :

```bash
pip install pyinstaller
pyinstaller --onefile --windowed \
    --add-data "requirements.txt:." \
    main.py
```

L'exécutable généré se trouve dans `dist/main` (Linux/macOS) ou
`dist\main.exe` (Windows). Il embarque Python et toutes les dépendances.

> **Note PyInstaller + PyQt6 :** Si l'exécutable ne trouve pas les plugins Qt,
> ajoutez `--collect-all PyQt6` à la commande PyInstaller.

---

## 🐛 Résolution des problèmes courants

| Problème | Solution |
|---|---|
| Dialogue de configuration ne s'ouvre pas | Vérifiez que PyQt6 est installé : `pip install PyQt6` |
| `soundcard` non disponible | `pip install soundcard` ou utiliser `LOOPBACK_DEVICE` |
| PDF non lisible | Vérifiez que `pypdf` est installé : `pip install pypdf` |
| Fenêtre invisible (macOS) | Vérifiez les permissions micro dans *Confidentialité → Micro* |
| Pas de réponse Gemini | Vérifiez votre connexion internet et la validité de la clé API |
| `ImportError: PyQt6` | `pip install PyQt6` |
| `ImportError: qasync` | `pip install qasync` |
| Clé API refusée (401) | Vérifiez que la clé est valide sur [Google AI Studio](https://aistudio.google.com/app/apikey) |

---

## 🚀 Améliorations possibles

### Fonctionnalités

- **Historique des réponses :** Sauvegarder automatiquement toutes les réponses Gemini dans un fichier texte ou JSON horodaté, pour pouvoir relire les échanges après l'entretien.
- **Raccourcis clavier globaux :** Ajouter des raccourcis (ex. `Ctrl+Espace` pour mettre en pause la capture, `Ctrl+C` pour copier la dernière réponse) via `pynput` ou `keyboard`.
- **Mode "Push-to-Talk" :** Envoyer l'audio uniquement lorsqu'une touche est maintenue enfoncée, pour économiser les tokens API et éviter les faux positifs.
- **Sélection du périphérique audio :** Ajouter dans le dialogue ⚙ la possibilité de choisir le micro et le périphérique loopback parmi les disponibles.
- **Support audio multilingue :** Permettre de configurer la langue de l'entretien pour que Gemini réponde dans la même langue que le recruteur.
- **Réponses audio TTS :** Activer la modalité `AUDIO` en retour de Gemini pour recevoir les suggestions directement dans l'oreillette, sans regarder l'écran.
- **Support DOCX :** Ajouter la lecture des fichiers `.docx` (CV Word) via `python-docx`.
- **Thèmes visuels :** Proposer plusieurs thèmes de couleur (clair/sombre/personnalisé) configurables.

### Architecture & Robustesse

- **Reconnexion automatique :** Implémenter une logique de retry avec backoff exponentiel si la connexion WebSocket est perdue pendant l'entretien.
- **Gestion des quotas API :** Détecter les erreurs de quota Gemini (HTTP 429) et afficher un message d'attente au lieu de planter.
- **Mixage audio intelligent :** Mixer les flux micro et loopback en un seul flux avant envoi pour réduire la consommation de tokens.
- **Détection de silence (VAD) :** Intégrer une détection d'activité vocale pour n'envoyer l'audio que lorsque quelqu'un parle.
- **Tests automatisés :** Ajouter des tests unitaires pour `audio_engine.py` (mock sounddevice) et `gemini_client.py` (mock WebSocket).
- **Chiffrement de la clé API :** Stocker la clé API chiffrée (avec `keyring` ou `cryptography`) plutôt qu'en clair dans `settings.json`.
- **Logging structuré :** Remplacer les `print()` par le module `logging` avec rotation de fichiers.

### Performance

- **Compression audio :** Encoder l'audio en Opus (via `opuslib`) avant envoi pour réduire la bande passante.
- **Buffer adaptatif :** Ajuster dynamiquement la taille des chunks audio selon la latence réseau mesurée.
- **Streaming de texte :** Afficher les tokens Gemini mot par mot au fur et à mesure, pour un rendu encore plus fluide.

---

## 📄 Licence

Ce projet est fourni à titre éducatif et expérimental.
Assurez-vous de respecter les [conditions d'utilisation de l'API Gemini](https://ai.google.dev/gemini-api/terms)
et les règles éthiques lors de son utilisation en entretien.
