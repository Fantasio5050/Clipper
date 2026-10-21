"""Transcription horodatée au mot avec locuteurs (Deepgram), mise en cache sur disque."""

import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from . import db, media
from .config import Config
from .journal import log

URL_DEEPGRAM = "https://api.deepgram.com/v1/listen"


def chemin_transcription(cfg: Config, youtube_id: str) -> Path:
    return cfg.dossier_video(youtube_id) / "transcription.json"


def charger(cfg: Config, youtube_id: str) -> dict:
    return json.loads(chemin_transcription(cfg, youtube_id).read_text(encoding="utf-8"))


def transcrire(cfg: Config, cnx, video) -> None:
    """Transcrit la vidéo une seule fois : si le cache existe, aucun appel n'est fait."""
    cache = chemin_transcription(cfg, video["youtube_id"])
    if cache.exists():
        log().info("[%s] Transcription déjà en cache", video["youtube_id"])
        db.maj_video(cnx, video["id"], etat="transcrit")
        return

    tr = cfg["transcription"]
    cle = cfg.cle("DEEPGRAM_API_KEY")
    audio = media.extraire_audio(Path(video["chemin_video"]), cfg.dossier_video(video["youtube_id"]) / "audio.m4a")
    log().info("[%s] Transcription Deepgram (%s, %s) de %.0f min d'audio…",
               video["youtube_id"], tr["modele"], tr["langue"], (video["duree"] or 0) / 60)
    brut = _appel_deepgram(cle, audio, tr["modele"], tr["langue"])

    temporaire = cache.with_suffix(".tmp")
    temporaire.write_text(json.dumps(brut, ensure_ascii=False), encoding="utf-8")
    minutes = brut.get("metadata", {}).get("duration", video["duree"] or 0) / 60
    with db.transaction(cnx):
        temporaire.replace(cache)
        db.ajouter_cout(cnx, video["id"], "transcription", minutes, "min", minutes * tr["tarif_minute"])
        db.maj_video(cnx, video["id"], etat="transcrit")
    log().info("[%s] Transcription terminée (%.0f min, ~%.3f $)", video["youtube_id"], minutes,
               minutes * tr["tarif_minute"])


def _appel_deepgram(cle: str, audio: Path, modele: str, langue: str) -> dict:
    params = urllib.parse.urlencode({
        "model": modele, "language": langue, "diarize": "true", "punctuate": "true",
        "smart_format": "true", "utterances": "false",
    })
    taille = audio.stat().st_size
    with audio.open("rb") as flux:
        requete = urllib.request.Request(
            f"{URL_DEEPGRAM}?{params}", data=flux, method="POST",
            headers={"Authorization": f"Token {cle}", "Content-Type": "audio/mp4", "Content-Length": str(taille)},
        )
        try:
            with urllib.request.urlopen(requete, timeout=1800) as rep:
                return json.load(rep)
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:300]
            raise RuntimeError(f"Deepgram a répondu {e.code} : {detail}") from None
