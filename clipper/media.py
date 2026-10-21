"""Appels à ffmpeg et ffprobe."""

import json
import subprocess
from pathlib import Path


class ErreurMedia(Exception):
    pass


def executer(cmd: list[str]) -> str:
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        fin = "\n".join(res.stderr.strip().splitlines()[-5:])
        raise ErreurMedia(f"{cmd[0]} a échoué : {fin}")
    return res.stdout


def duree(chemin: Path) -> float:
    sortie = executer(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(chemin)])
    return float(json.loads(sortie)["format"]["duration"])


def extraire_audio(source: Path, destination: Path) -> Path:
    """Piste audio mono en AAC 64 kb/s : suffisant pour la transcription, léger à envoyer."""
    if destination.exists() and destination.stat().st_size > 0:
        return destination
    temporaire = destination.with_suffix(".tmp" + destination.suffix)
    executer(["ffmpeg", "-y", "-v", "error", "-i", str(source), "-vn", "-ac", "1", "-c:a", "aac",
              "-b:a", "64k", str(temporaire)])
    temporaire.replace(destination)
    return destination
