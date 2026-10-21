"""Journalisation en français, vers la console et data/clipper.log."""

import logging
from pathlib import Path

FORMAT = "%(asctime)s %(levelname)-7s %(message)s"
NIVEAUX = {"DEBUG": "DÉBOGAGE", "INFO": "INFO", "WARNING": "ATTENTION", "ERROR": "ERREUR", "CRITICAL": "CRITIQUE"}


class _FormatFr(logging.Formatter):
    def format(self, record):
        record.levelname = NIVEAUX.get(record.levelname, record.levelname)
        return super().format(record)


def configurer(dossier: Path, verbeux: bool = False) -> None:
    dossier.mkdir(parents=True, exist_ok=True)
    racine = logging.getLogger()
    racine.setLevel(logging.DEBUG if verbeux else logging.INFO)
    racine.handlers.clear()
    fmt = _FormatFr(FORMAT, datefmt="%Y-%m-%d %H:%M:%S")
    console = logging.StreamHandler()
    console.setFormatter(fmt)
    fichier = logging.FileHandler(dossier / "clipper.log", encoding="utf-8")
    fichier.setFormatter(fmt)
    racine.addHandler(console)
    racine.addHandler(fichier)
    # Les bibliothèques tierces restent discrètes.
    for nom in ("httpx", "httpx2", "anthropic", "urllib3"):
        logging.getLogger(nom).setLevel(logging.WARNING)


def log(nom: str = "clipper") -> logging.Logger:
    return logging.getLogger(nom)
