"""Pipeline complet sur un fichier local, avec Deepgram et Claude simulés."""

import json

import pytest

from clipper import db, ingest, transcribe
from clipper.pipeline import Pipeline


@pytest.fixture
def video_locale(cfg, cnx, tmp_path, monkeypatch):
    fichier = tmp_path / "podcast.mp4"
    fichier.write_bytes(b"x")
    monkeypatch.setattr(ingest.media, "duree", lambda chemin: 1800.0)
    monkeypatch.setattr(transcribe.media, "extraire_audio", lambda src, dst: dst)
    for v in ingest.developper_url(cfg, str(fichier)):
        db.ajouter_video(cnx, v["youtube_id"], v["url"], v["titre"], v["duree"])
    return db.videos(cnx)[0]


def deepgram_factice(*args):
    # 300 phrases de 5 s : « Phrase n. »
    mots = [{"word": f"p{i}", "punctuated_word": f"Phrase{i}.", "start": i * 6.0, "end": i * 6.0 + 5,
             "speaker": 0} for i in range(300)]
    return {"metadata": {"duration": 1800.0}, "results": {"channels": [{"alternatives": [{"words": mots}]}]}}


class LLMFactice:
    def __init__(self, reponses):
        self.reponses = list(reponses)
        self.appels = 0

    def json(self, **kwargs):
        self.appels += 1
        assert "{{" not in kwargs["systeme"], "variable de prompt non remplie"
        return self.reponses.pop(0)


def test_pipeline_bout_en_bout(cfg, cnx, video_locale, monkeypatch):
    monkeypatch.setenv("DEEPGRAM_API_KEY", "factice")
    appels_deepgram = []
    monkeypatch.setattr(transcribe, "_appel_deepgram", lambda *a: appels_deepgram.append(1) or deepgram_factice())
    reponse = json.dumps({"candidats": [
        {"phrase_debut": 10, "phrase_fin": 40, "sujet": "A", "note": 80, "raison": "r"},
        {"phrase_debut": 12, "phrase_fin": 38, "sujet": "A bis", "note": 60, "raison": "r"},  # chevauche A
        {"phrase_debut": 100, "phrase_fin": 140, "sujet": "B", "note": 90, "raison": "r"},
    ]})
    pipeline = Pipeline(cfg, cnx)
    pipeline._llm = LLMFactice([reponse])

    assert pipeline.executer() == (1, 0)
    v = db.video(cnx, video_locale["id"])
    assert v["etat"] == "selectionne"
    clips = db.clips(cnx, v["id"])
    assert [c["sujet"] for c in clips] == ["A", "B"]
    assert clips[0]["debut"] == 60.0 and clips[0]["fin"] == 245.0
    assert db.cout_video(cnx, v["id"]) > 0  # transcription comptée

    # Relancer ne refait rien : ni Deepgram, ni Claude.
    assert pipeline.executer() == (0, 0)
    assert len(appels_deepgram) == 1 and pipeline._llm.appels == 1


def test_echec_isole_et_reprise(cfg, cnx, video_locale, monkeypatch):
    monkeypatch.setenv("DEEPGRAM_API_KEY", "factice")
    db.ajouter_video(cnx, "autre", "https://www.youtube.com/watch?v=autre", "Autre", 1800)

    def deepgram_en_panne(*a):
        raise RuntimeError("Deepgram a répondu 503")

    monkeypatch.setattr(transcribe, "_appel_deepgram", deepgram_en_panne)
    vrai_telecharger = ingest.telecharger

    def telecharger(cfg, cnx, v):
        if v["youtube_id"] != "autre":
            return vrai_telecharger(cfg, cnx, v)
        db.maj_video(cnx, v["id"], etat="ignoree")

    monkeypatch.setattr(ingest, "telecharger", telecharger)
    pipeline = Pipeline(cfg, cnx)
    pipeline._llm = LLMFactice([])

    ok, echecs = pipeline.executer()
    assert (ok, echecs) == (1, 1)  # la vidéo en panne ne bloque pas l'autre
    v = db.video(cnx, video_locale["id"])
    assert v["etat"] == "telecharge" and "503" in v["erreur"] and v["tentatives"] == 1

    # Le service revient : la reprise repart de l'étape échouée et efface l'erreur.
    monkeypatch.setattr(transcribe, "_appel_deepgram", lambda *a: deepgram_factice())
    pipeline._llm = LLMFactice([json.dumps({"candidats": []})])
    assert pipeline.executer() == (1, 0)
    v = db.video(cnx, video_locale["id"])
    assert v["etat"] == "selectionne" and v["erreur"] is None


def test_abandon_apres_tentatives_max(cfg, cnx, video_locale):
    db.maj_video(cnx, video_locale["id"], erreur="boom", tentatives=cfg["execution"]["tentatives_max"])
    assert Pipeline(cfg, cnx).executer() == (0, 0)
