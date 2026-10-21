"""Chargement de config.yaml et du fichier .env."""

import os
from dataclasses import dataclass
from pathlib import Path

import yaml


class ErreurConfig(Exception):
    pass


def charger_env(chemin: Path) -> None:
    """Lit un fichier .env (CLE=valeur) sans écraser les variables déjà définies."""
    if not chemin.exists():
        return
    for ligne in chemin.read_text(encoding="utf-8").splitlines():
        ligne = ligne.strip()
        if not ligne or ligne.startswith("#") or "=" not in ligne:
            continue
        cle, valeur = ligne.split("=", 1)
        valeur = valeur.strip().strip('"').strip("'")
        if valeur:
            os.environ.setdefault(cle.strip(), valeur)


@dataclass
class Config:
    racine: Path  # dossier contenant config.yaml
    brut: dict

    def __getitem__(self, cle):
        return self.brut[cle]

    @property
    def dossier_donnees(self) -> Path:
        return self.racine / self.brut.get("dossier_donnees", "data")

    @property
    def dossier_prompts(self) -> Path:
        return self.racine / self.brut.get("dossier_prompts", "prompts")

    @property
    def chemin_db(self) -> Path:
        return self.dossier_donnees / "clipper.db"

    def dossier_video(self, youtube_id: str) -> Path:
        return self.dossier_donnees / "videos" / youtube_id

    def prompt(self, nom: str) -> str:
        chemin = self.dossier_prompts / f"{nom}.md"
        if not chemin.exists():
            raise ErreurConfig(f"Prompt introuvable : {chemin}")
        return chemin.read_text(encoding="utf-8")

    def cle(self, nom: str) -> str:
        valeur = os.environ.get(nom, "")
        if not valeur:
            raise ErreurConfig(f"{nom} manquante : ajoute-la dans le fichier .env")
        return valeur


def charger(chemin: str | Path | None = None) -> Config:
    chemin = Path(chemin or os.environ.get("CLIPPER_CONFIG", "config.yaml")).resolve()
    if not chemin.exists():
        raise ErreurConfig(f"Fichier de configuration introuvable : {chemin}")
    brut = yaml.safe_load(chemin.read_text(encoding="utf-8")) or {}
    charger_env(chemin.parent / ".env")
    return Config(racine=chemin.parent, brut=brut)
