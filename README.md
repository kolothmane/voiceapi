# 🎙 Interview Assistant – Assistant d'entretien en temps réel

Application de bureau furtive qui écoute votre micro **et** le son de vos haut-parleurs,
envoie ces flux audio à l'**API Gemini Live**, et affiche les réponses dans une fenêtre
flottante semi-transparente, toujours au premier plan.

> **Cas d'usage typique :** entretien de stage ou d'embauche en visio-conférence.
> L'assistant souffle des réponses courtes et techniques en temps réel.

---

## 📁 Architecture du projet

```
voiceapi/
├── config.py          # Clé API, constantes audio et UI, prompt système
├── audio_engine.py    # Capture micro + loopback (sounddevice / soundcard)
├── gemini_client.py   # Client WebSocket Gemini Multimodal Live
├── ui.py              # Fenêtre overlay PyQt6 (sans bordures, transparente)
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

### Étape 5 – Obtenir et configurer la clé API Gemini

1. Rendez-vous sur [Google AI Studio](https://aistudio.google.com/app/apikey).
2. Cliquez sur **Create API key** et copiez la clé générée.
3. Définissez la variable d'environnement `GEMINI_API_KEY` :

**Windows (PowerShell) :**
```powershell
$env:GEMINI_API_KEY = "AIzaSy..."
```

**Windows (Invite de commandes, permanent) :**
```cmd
setx GEMINI_API_KEY "AIzaSy..."
```

**Linux / macOS :**
```bash
export GEMINI_API_KEY="AIzaSy..."
# Pour rendre permanent, ajoutez la ligne ci-dessus à ~/.bashrc ou ~/.zshrc
```

> ⚠️ Ne committez **jamais** votre clé API dans un dépôt Git.

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

### Étape 7 – Lancer l'application

```bash
python main.py
```

Une fenêtre flottante semi-transparente apparaît en haut à droite de l'écran.
Commencez votre entretien : l'assistant écoute et affiche ses suggestions en temps réel.

**Contrôles de la fenêtre :**

| Action | Comment |
|---|---|
| Déplacer la fenêtre | Clic gauche maintenu + glisser |
| Effacer le texte | Bouton 🗑 |
| Fermer l'application | Bouton ✕ |

---

### Étape 8 – Personnaliser le prompt système (optionnel)

Ouvrez `config.py` et modifiez la constante `SYSTEM_PROMPT` pour adapter
l'assistant à votre secteur, votre poste cible, ou votre style de réponse souhaité.

```python
SYSTEM_PROMPT = (
    "Tu es un assistant furtif. Ton rôle est d'écouter la conversation et de me "
    "souffler des réponses courtes, percutantes et techniques. ..."
)
```

---

## 🐛 Résolution des problèmes courants

| Problème | Solution |
|---|---|
| `GEMINI_API_KEY not set` | Voir Étape 5 |
| `soundcard` non disponible | `pip install soundcard` ou utiliser `LOOPBACK_DEVICE` |
| Fenêtre invisible (macOS) | Vérifiez les permissions micro dans *Confidentialité → Micro* |
| Pas de réponse Gemini | Vérifiez votre connexion internet et la validité de la clé API |
| `ImportError: PyQt6` | `pip install PyQt6` |
| `ImportError: qasync` | `pip install qasync` |

---

## 🚀 Améliorations possibles

### Fonctionnalités

- **Historique des réponses :** Sauvegarder automatiquement toutes les réponses Gemini dans un fichier texte ou JSON horodaté, pour pouvoir relire les échanges après l'entretien.
- **Raccourcis clavier globaux :** Ajouter des raccourcis (ex. `Ctrl+Espace` pour mettre en pause la capture, `Ctrl+C` pour copier la dernière réponse) via `pynput` ou `keyboard`.
- **Mode "Push-to-Talk" :** Envoyer l'audio uniquement lorsqu'une touche est maintenue enfoncée, pour économiser les tokens API et éviter les faux positifs.
- **Sélection du périphérique audio :** Ajouter une fenêtre de configuration au démarrage pour choisir le micro et le périphérique loopback parmi les disponibles.
- **Support audio multilingue :** Permettre de configurer la langue de l'entretien pour que Gemini réponde dans la même langue que le recruteur.
- **Réponses audio TTS :** Activer la modalité `AUDIO` en retour de Gemini pour recevoir les suggestions directement dans l'oreillette, sans regarder l'écran.
- **Thèmes visuels :** Proposer plusieurs thèmes de couleur (clair/sombre/personnalisé) configurables dans `config.py`.
- **Fenêtre de configuration graphique :** Remplacer les variables d'environnement par un formulaire Qt pour saisir la clé API, choisir les périphériques et modifier le prompt.

### Architecture & Robustesse

- **Reconnexion automatique :** Implémenter une logique de retry avec backoff exponentiel si la connexion WebSocket est perdue pendant l'entretien.
- **Gestion des quotas API :** Détecter les erreurs de quota Gemini (HTTP 429) et afficher un message d'attente au lieu de planter.
- **Mixage audio intelligent :** Mixer les flux micro et loopback en un seul flux avant envoi (plutôt que deux flux distincts) pour réduire la consommation de tokens.
- **Détection de silence (VAD) :** Intégrer une détection d'activité vocale (Voice Activity Detection) pour n'envoyer l'audio que lorsque quelqu'un parle, réduisant ainsi les coûts et la latence.
- **Tests automatisés :** Ajouter des tests unitaires pour `audio_engine.py` (mock sounddevice) et `gemini_client.py` (mock WebSocket), et des tests d'intégration avec un serveur WebSocket local.
- **Packaging en exécutable :** Utiliser `PyInstaller` ou `cx_Freeze` pour générer un `.exe` (Windows) ou `.app` (macOS) distribuable, sans nécessiter d'installation Python.
- **Chiffrement de la clé API :** Stocker la clé API chiffrée (avec `keyring` ou `cryptography`) plutôt qu'en variable d'environnement en clair.
- **Logging structuré :** Remplacer les `print()` par le module `logging` avec rotation de fichiers, pour faciliter le débogage en production.

### Performance

- **Compression audio :** Encoder l'audio en Opus (via `opuslib`) avant envoi pour réduire la bande passante, si Gemini l'accepte.
- **Buffer adaptatif :** Ajuster dynamiquement la taille des chunks audio selon la latence réseau mesurée.
- **Streaming de texte :** Afficher les tokens Gemini mot par mot au fur et à mesure (streaming partiel), pour un rendu encore plus fluide.

---

## 📄 Licence

Ce projet est fourni à titre éducatif et expérimental.
Assurez-vous de respecter les [conditions d'utilisation de l'API Gemini](https://ai.google.dev/gemini-api/terms)
et les règles éthiques lors de son utilisation en entretien.
