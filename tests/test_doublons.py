"""Aucune vidéo ni transcription traitée deux fois."""

from clipper import db, ingest, transcribe


def test_meme_video_ajoutee_deux_fois(cnx):
    assert db.ajouter_video(cnx, "abc123", "https://www.youtube.com/watch?v=abc123") is True
    assert db.ajouter_video(cnx, "abc123", "https://youtu.be/abc123") is False
    assert len(db.videos(cnx)) == 1


def test_playlist_contenant_une_video_deja_presente(cnx):
    db.ajouter_video(cnx, "v2", "u2")
    nouvelles = sum(db.ajouter_video(cnx, i, f"u{i}") for i in ("v1", "v2", "v3"))
    assert nouvelles == 2
    assert [v["youtube_id"] for v in db.videos(cnx)] == ["v2", "v1", "v3"]


def test_doublon_ne_reinitialise_pas_l_etat(cnx):
    db.ajouter_video(cnx, "v1", "u1")
    v = db.videos(cnx)[0]
    db.maj_video(cnx, v["id"], etat="selectionne")
    db.ajouter_video(cnx, "v1", "u1")
    assert db.video(cnx, v["id"])["etat"] == "selectionne"


def test_aplatir_playlist_imbriquee():
    info = {"_type": "playlist", "entries": [
        {"_type": "playlist", "entries": [{"id": "a", "title": "A", "duration": 3600}]},
        {"id": "b", "title": "B"},
        None,
        {"ie_key": "YoutubeTab", "id": "UCxxx", "url": "https://www.youtube.com/@x/shorts"},
    ]}
    assert [v["youtube_id"] for v in ingest._aplatir(info)] == ["a", "b"]


def test_url_de_chaine_vise_l_onglet_videos():
    assert ingest.normaliser_url("https://www.youtube.com/@chaine") == "https://www.youtube.com/@chaine/videos"
    assert ingest.normaliser_url("https://www.youtube.com/@chaine/streams") == "https://www.youtube.com/@chaine/streams"
    assert ingest.normaliser_url("https://www.youtube.com/watch?v=x") == "https://www.youtube.com/watch?v=x"


def test_transcription_en_cache_jamais_refaite(cfg, cnx, monkeypatch):
    db.ajouter_video(cnx, "v1", "u1")
    v = db.videos(cnx)[0]
    cache = transcribe.chemin_transcription(cfg, "v1")
    cache.parent.mkdir(parents=True)
    cache.write_text("{}")

    def interdit(*a, **k):
        raise AssertionError("Deepgram ne doit pas être appelé")

    monkeypatch.setattr(transcribe, "_appel_deepgram", interdit)
    monkeypatch.setattr(transcribe.media, "extraire_audio", interdit)
    transcribe.transcrire(cfg, cnx, v)
    assert db.video(cnx, v["id"])["etat"] == "transcrit"
    assert db.cout_video(cnx, v["id"]) == 0
