from pathlib import Path

import pytest

from clipper import db
from clipper.config import Config
from clipper.transcript import Phrase

RACINE = Path(__file__).resolve().parent.parent


@pytest.fixture
def cnx(tmp_path):
    connexion = db.connecter(tmp_path / "test.db")
    yield connexion
    connexion.close()


@pytest.fixture
def cfg(tmp_path):
    import yaml
    brut = yaml.safe_load((RACINE / "config.yaml").read_text(encoding="utf-8"))
    brut["dossier_donnees"] = str(tmp_path / "data")
    brut["dossier_prompts"] = str(RACINE / "prompts")
    return Config(racine=tmp_path, brut=brut)


def faire_phrases(n: int, duree: float = 10.0) -> list[Phrase]:
    """n phrases consécutives de `duree` secondes, séparées de 0,5 s."""
    return [Phrase(i, i * (duree + 0.5), i * (duree + 0.5) + duree, i % 2, f"Phrase {i}.") for i in range(n)]
