"""Ingestion : développe une URL (vidéo, playlist, chaîne) et télécharge les vidéos."""

import hashlib
import json
import re
from pathlib import Path

import yt_dlp

from . import db, media
from .config import Config
from .journal import log

# Une URL de chaîne sans onglet : on vise l'onglet « Vidéos » (les Shorts ne nous intéressent pas).
RE_CHAINE = re.compile(r"^https?://(www\.)?youtube\.com/(@[^/?#]+|channel/[^/?#]+|c/[^/?#]+|user/[^/?#]+)/?$")


class _JournalYtdlp:
    """Redirige les messages de yt-dlp vers notre journal, sans le bruit de progression."""

    def debug(self, msg):
        pass

    def info(self, msg):
        pass

    def warning(self, msg):
        log().debug("yt-dlp : %s", msg)

    def error(self, msg):
        log().error("yt-dlp : %s", msg)


def _options(cfg: Config, **autres) -> dict:
    ing = cfg["ingestion"]
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "logger": _JournalYtdlp(),
        "js_runtimes": {nom: {} for nom in ing.get("js_runtimes", ["deno"])},
    }
    if ing.get("cookies"):
        opts["cookiefile"] = str(cfg.racine / ing["cookies"])
    opts.update(autres)
    return opts


def id_local(chemin: Path) -> str:
    return "local-" + hashlib.sha1(str(chemin.resolve()).encode()).hexdigest()[:12]


def normaliser_url(url: str) -> str:
    url = url.strip()
    if RE_CHAINE.match(url):
        return url.rstrip("/") + "/videos"
    return url


def developper_url(cfg: Config, url: str) -> list[dict]:
    """Liste les vidéos derrière une URL : [{youtube_id, url, titre, duree}]."""
    chemin = Path(url).expanduser()
    if chemin.exists():
        return [{"youtube_id": id_local(chemin), "url": str(chemin.resolve()), "titre": chemin.stem,
                 "duree": media.duree(chemin)}]

    with yt_dlp.YoutubeDL(_options(cfg, extract_flat="in_playlist", skip_download=True)) as ydl:
        info = ydl.extract_info(normaliser_url(url), download=False)
    return list(_aplatir(info))


def _aplatir(info: dict, profondeur: int = 0):
    if info.get("_type") in ("playlist", "multi_video") and profondeur < 3:
        for entree in info.get("entries") or []:
            if entree:
                yield from _aplatir(entree, profondeur + 1)
        return
    if info.get("ie_key") == "YoutubeTab" or not info.get("id"):
        return  # onglet de chaîne non développé ou entrée vide
    yield {
        "youtube_id": info["id"],
        "url": f"https://www.youtube.com/watch?v={info['id']}",
        "titre": info.get("title"),
        "duree": info.get("duration"),
    }


def telecharger(cfg: Config, cnx, video) -> bool:
    """Télécharge la vidéo si besoin. Renvoie False si elle est ignorée (trop courte)."""
    dossier = cfg.dossier_video(video["youtube_id"])
    dossier.mkdir(parents=True, exist_ok=True)
    duree_min = cfg["ingestion"].get("duree_min_source_min", 0) * 60

    if video["youtube_id"].startswith("local-"):
        source = Path(video["url"])
        duree = media.duree(source)
        db.maj_video(cnx, video["id"], chemin_video=str(source), duree=duree, etat="telecharge")
        return True

    existant = _fichier_source(dossier)
    if existant is None:
        if video["duree"] and video["duree"] < duree_min:
            return _ignorer(cnx, video, video["duree"])
        log().info("[%s] Téléchargement de « %s »", video["youtube_id"], video["titre"] or video["url"])
        hauteur = cfg["ingestion"].get("hauteur_max", 1080)
        opts = _options(
            cfg,
            format=f"bv*[height<={hauteur}]+ba/b[height<={hauteur}]/bv*+ba/b",
            merge_output_format="mp4",
            outtmpl=str(dossier / "source.%(ext)s"),
            writeinfojson=True,
            continuedl=True,
        )
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.extract_info(video["url"], download=True)
        except yt_dlp.utils.DownloadError as e:
            if any(s in str(e) for s in ("403", "Sign in", "LOGIN_REQUIRED", "not a bot")):
                raise RuntimeError(f"{e} → YouTube demande une connexion : exporte tes cookies "
                                   "(cookies.txt) et renseigne ingestion.cookies dans config.yaml") from None
            raise
        existant = _fichier_source(dossier)
        if existant is None:
            raise RuntimeError("yt-dlp n'a produit aucun fichier vidéo")
    else:
        log().info("[%s] Vidéo déjà téléchargée, on la réutilise", video["youtube_id"])

    meta = _lire_info(dossier)
    duree = meta.get("duration") or media.duree(existant)
    if duree < duree_min:
        return _ignorer(cnx, video, duree)
    db.maj_video(cnx, video["id"], chemin_video=str(existant), titre=meta.get("title") or video["titre"],
                 chaine=meta.get("channel") or meta.get("uploader"), duree=duree, etat="telecharge")
    return True


def _fichier_source(dossier: Path) -> Path | None:
    for ext in ("mp4", "mkv", "webm"):
        f = dossier / f"source.{ext}"
        if f.exists() and f.stat().st_size > 0:
            return f
    return None


def _lire_info(dossier: Path) -> dict:
    f = dossier / "source.info.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}


def _ignorer(cnx, video, duree: float) -> bool:
    log().info("[%s] Ignorée : %.0f min, sous le seuil de durée", video["youtube_id"], duree / 60)
    db.maj_video(cnx, video["id"], duree=duree, etat="ignoree")
    return False
