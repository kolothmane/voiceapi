# Interview Voice Simulator (Web / Vercel)

Application web moderne pour simuler un entretien vocal avec Gemini.

## Fonctionnalités
- Paramètres entretien : type, poste, description, durée.
- Entrée vocale via micro navigateur (Web Speech API).
- Réponses audio (speech synthesis du navigateur).
- Import de CV (`.pdf`, `.doc`, `.docx`, `.txt`) avec extraction automatique du texte.
- Compte rendu final automatique à la fin du timer.
- Clé Gemini côté serveur via `GEMINI_API_KEY`.
- Modèle par défaut : `models/gemini-2.5-flash` (modifiable via `GEMINI_MODEL`).

## Lancer en local
```bash
npm install
GEMINI_API_KEY=... npm run dev
```

## Déploiement Vercel
1. Importer le repo.
2. Ajouter la variable d'environnement `GEMINI_API_KEY`.
3. (Optionnel) Ajouter `GEMINI_MODEL=models/gemini-2.5-flash`.
4. Déployer.
