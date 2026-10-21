"""Enchaînement des étapes par vidéo, avec reprise et isolation des erreurs."""

import sys
import traceback
from contextlib import contextmanager

from . import db, ingest, selection, transcribe
from .config import Config, ErreurConfig
from .journal import log
from .llm import ClientLLM

ETATS_FINAUX = ("selectionne", "ignoree")


@contextmanager
def verrou(cfg: Config):
    """Empêche deux `clipper run` simultanés sur les mêmes données."""
    chemin = cfg.dossier_donnees / "clipper.lock"
    chemin.parent.mkdir(parents=True, exist_ok=True)
    with chemin.open("w") as f:
        if sys.platform != "win32":
            import fcntl
            try:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise SystemExit("Un autre `clipper run` est déjà en cours.") from None
        yield


class Pipeline:
    def __init__(self, cfg: Config, cnx):
        self.cfg = cfg
        self.cnx = cnx
        self._llm = None

    @property
    def llm(self) -> ClientLLM:
        # Créé à la demande : une clé Anthropic absente ne bloque pas téléchargement ni transcription.
        if self._llm is None:
            self._llm = ClientLLM(self.cfg, self.cnx)
        return self._llm

    def etape(self, video) -> None:
        etat = video["etat"]
        if etat == "en_attente":
            ingest.telecharger(self.cfg, self.cnx, video)
        elif etat == "telecharge":
            transcribe.transcrire(self.cfg, self.cnx, video)
        elif etat == "transcrit":
            selection.selectionner(self.cfg, self.cnx, video, self.llm)
        else:
            raise RuntimeError(f"État inconnu : {etat}")

    def traiter(self, video) -> bool:
        """Fait avancer une vidéo jusqu'au bout. Renvoie False en cas d'échec (enregistré en base)."""
        try:
            while video["etat"] not in ETATS_FINAUX:
                self.etape(video)
                video = db.video(self.cnx, video["id"])
            if video["erreur"]:
                db.maj_video(self.cnx, video["id"], erreur=None, tentatives=0)
            return True
        except (KeyboardInterrupt, ErreurConfig):
            raise  # problème global (clé manquante…) : inutile de griller les tentatives des autres vidéos
        except Exception as e:
            log().error("[%s] Échec à l'étape « %s » : %s", video["youtube_id"], video["etat"], e)
            log().debug(traceback.format_exc())
            db.maj_video(self.cnx, video["id"], erreur=str(e)[:500], tentatives=video["tentatives"] + 1)
            return False

    def executer(self, forcer: bool = False) -> tuple[int, int]:
        max_tentatives = self.cfg["execution"]["tentatives_max"]
        ok = echecs = 0
        for video in db.videos(self.cnx):
            if video["etat"] in ETATS_FINAUX:
                continue
            if video["erreur"] and video["tentatives"] >= max_tentatives and not forcer:
                log().warning("[%s] Abandonnée après %d échecs (relance : clipper run --forcer)",
                              video["youtube_id"], video["tentatives"])
                continue
            if self.traiter(video):
                ok += 1
            else:
                echecs += 1
        return ok, echecs
