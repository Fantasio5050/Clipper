# Clipper

Tu colles l'URL d'une vidéo, d'une playlist ou d'une chaîne YouTube. Clipper en tire des extraits horizontaux de 2 à 5 minutes, chacun avec une note, des titres et une miniature. Tu valides en un clic, et les clips validés partent dans une file de publication programmée sur ta chaîne de clips.

> État : **phase 1** (ingestion, transcription, sélection). Revue, découpe et miniatures arrivent en phase 2, la publication en phase 3, le suivi en phase 4.

## Installation pas à pas

### 1. Prérequis système
- **Python 3.11 ou plus récent** : `python3 --version`
- **ffmpeg** (fournit aussi ffprobe) :
  - macOS : `brew install ffmpeg`
  - Ubuntu/Debian : `sudo apt install ffmpeg`
  - Windows : `winget install ffmpeg`
- **deno**, le runtime JavaScript dont yt-dlp a besoin pour YouTube :
  - macOS/Linux : `curl -fsSL https://deno.land/install.sh | sh`
  - Windows : `winget install deno`
  - Si Node.js ≥ 20 est déjà installé, il suffit (voir `ingestion.js_runtimes` dans config.yaml).

### 2. Installer Clipper
```bash
git clone <ton-depot> clipper && cd clipper
python3 -m venv .venv
source .venv/bin/activate          # Windows : .venv\Scripts\activate
pip install -e ".[dev]"
```

### 3. Clés API
```bash
cp .env.example .env
```
Puis remplis `.env` :
- `ANTHROPIC_API_KEY` : sur https://console.anthropic.com/settings/keys
- `DEEPGRAM_API_KEY` : sur https://console.deepgram.com, rubrique *API Keys*

### 4. Vérifier
```bash
python -m pytest -q
clipper status
```

## Utilisation
```bash
clipper add "https://www.youtube.com/watch?v=…"   # une vidéo
clipper add "https://www.youtube.com/playlist?list=…"
clipper add "https://www.youtube.com/@chaine"    # toutes les vidéos de la chaîne (sans les Shorts)
clipper add ~/Videos/episode-12.mp4              # un fichier local

clipper run          # télécharge, transcrit, sélectionne (reprend où il s'était arrêté)
clipper status       # état et coût par vidéo, plus le cumul
clipper status 3     # candidats de la vidéo n° 3 : note, bornes, sujet, raison
```

Toutes les commandes sont idempotentes. Une vidéo n'est jamais téléchargée ni transcrite deux fois, et en cas de crash ou de Ctrl+C, il suffit de relancer `clipper run`. Une vidéo en erreur n'empêche pas les autres d'avancer : elle est retentée à chaque `run`, au maximum `execution.tentatives_max` fois (ensuite `clipper run --forcer`).

## Réglages
- `config.yaml` : tous les réglages, commentés (modèle, nombre de candidats, durées, tarifs…).
- `prompts/selection.md` : le prompt de sélection. Il se modifie sans toucher au code. Variables disponibles : `{{titre}}`, `{{chaine}}`, `{{duree}}`, `{{portee}}`, `{{nb_min}}`, `{{nb_max}}`, `{{duree_min}}`, `{{duree_max}}`.

## Coûts
`clipper status` affiche une estimation par vidéo, calculée à partir des jetons réellement consommés et des minutes transcrites, avec les tarifs de `config.yaml`. Ordre de grandeur pour 1 h de vidéo : environ 0,26 $ de transcription Deepgram et 0,10 à 0,20 $ de Claude Sonnet 5.5.

## Dépannage
- **« YouTube demande une connexion » / HTTP 403** : YouTube soupçonne un robot, surtout depuis un serveur ou un VPN. Exporte tes cookies YouTube au format Netscape (extension « Get cookies.txt LOCALLY »), enregistre-les dans `cookies.txt` à la racine, puis mets `cookies: cookies.txt` dans `config.yaml`.
- **Journal complet** : `data/clipper.log` (`clipper -v run` pour le détail).
