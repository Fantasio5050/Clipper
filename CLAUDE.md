# Clipper

## But
Transformer des vidéos YouTube longues (podcasts, interviews, formations) en extraits horizontaux de 2 à 5 min, les faire valider dans une page locale, puis les publier en file programmée sur une chaîne YouTube de clips. Tout tourne en local (pas de cloud en v1).

## Stack
- Python ≥ 3.11, SQLite (module standard), argparse.
- yt-dlp (+ yt-dlp-ejs, runtime JS deno ou node) pour l'ingestion.
- Deepgram nova-3 en REST (urllib, pas de SDK) pour la transcription au mot avec locuteurs.
- SDK `anthropic` pour la sélection et les titres (`claude-sonnet-5-5`, sortie JSON structurée, repli serveur en cas de refus).
- ffmpeg/ffprobe en sous-processus.
- À venir : FastAPI + Jinja2 (revue), Pillow + opencv-python-headless (miniatures), google-api-python-client + google-auth-oauthlib (YouTube Data v3 et Analytics v2).

## Commandes
```bash
pip install -e ".[dev]"      # installation
python -m pytest -q          # tests
clipper add URL              # vidéo, playlist, chaîne ou fichier local
clipper run                  # fait avancer toutes les vidéos (idempotent, reprise après crash)
clipper status [N]           # état + coûts ; avec N : candidats de la vidéo N
clipper review | publish | stats   # phases 2 à 4
```

## Architecture
- `clipper/cli.py` : commandes. `pipeline.py` : machine à états par vidéo (`en_attente` → `telecharge` → `transcrit` → `selectionne`, ou `ignoree`), verrou de fichier, erreurs isolées par vidéo (colonne `erreur`, `tentatives`).
- `ingest.py` (yt-dlp), `transcribe.py` (Deepgram, cache `data/videos/<id>/transcription.json`), `transcript.py` (mots → phrases numérotées), `selection.py` (blocs, parsing, fusion), `llm.py` (appels Claude + coûts), `db.py` (schéma par migrations), `media.py` (ffmpeg).
- Prompts : `prompts/*.md`, variables `{{nom}}`. Claude désigne les extraits par **numéros de phrase**, convertis ensuite en temps.
- Données : `data/` (ignoré par git) : `clipper.db`, `clipper.log`, `videos/<youtube_id>/`.

## Conventions
- Code, commentaires, logs et messages en français. Identifiants en français sans accents.
- Chaque étape vérifie l'état et ses fichiers avant d'agir : jamais de retéléchargement ni de retranscription. Les fichiers sont écrits en `.tmp` puis renommés, et les écritures en base se font dans `db.transaction`.
- Tout réglage va dans `config.yaml` (commenté) et les secrets dans `.env`. Aucune valeur en dur dans le code.
- Ajouter une colonne ou une table = ajouter une entrée à `db.MIGRATIONS` (ne jamais modifier une migration existante).
- Pas de dépendance nouvelle sans raison claire.
- Tests obligatoires pour : bornes, parsing de la sortie Claude, quota, doublons.

## Notes
- Depuis un datacenter, YouTube bloque souvent le téléchargement (« LOGIN_REQUIRED », 403). Remède : `ingestion.cookies` dans config.yaml, ou fichier local.
- `anthropic.base_url` est fixée dans config.yaml pour ignorer un éventuel `ANTHROPIC_BASE_URL` de l'environnement.
