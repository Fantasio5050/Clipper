"""Parsing de la sortie de Claude, découpe en blocs, fusion et chevauchement."""

import json

import pytest

from clipper.llm import ErreurLLM, extraire_json
from clipper.selection import blocs, chevauchement, fusionner, parser_candidats, remplir
from tests.conftest import faire_phrases

PHRASES = faire_phrases(100)


def cand(i0, i1, note=80, sujet="Un sujet", raison="Une raison"):
    return {"phrase_debut": i0, "phrase_fin": i1, "note": note, "sujet": sujet, "raison": raison}


def rep(*candidats):
    return json.dumps({"candidats": list(candidats)})


# --- Parsing ---------------------------------------------------------------

def test_parsing_nominal():
    res = parser_candidats(rep(cand(10, 25, 85)), PHRASES)
    assert len(res) == 1
    assert res[0]["debut_llm"] == PHRASES[10].debut
    assert res[0]["fin_llm"] == PHRASES[25].fin
    assert res[0]["note"] == 85


def test_parsing_json_entoure_de_texte():
    texte = "Voici les extraits :\n```json\n" + rep(cand(1, 5)) + "\n```\nBonne journée."
    assert len(parser_candidats(texte, PHRASES)) == 1


def test_parsing_sans_json():
    with pytest.raises(ErreurLLM):
        parser_candidats("Je n'ai rien trouvé.", PHRASES)


def test_parsing_json_casse():
    with pytest.raises(ErreurLLM):
        extraire_json('{"candidats": [ {"phrase_debut": 1, }')


def test_parsing_sans_liste_candidats():
    with pytest.raises(ErreurLLM):
        parser_candidats('{"extraits": []}', PHRASES)


def test_parsing_champs_manquants_ecartes():
    incomplet = {"phrase_debut": 1, "phrase_fin": 5, "note": 70}  # ni sujet ni raison
    res = parser_candidats(rep(incomplet, cand(10, 20)), PHRASES)
    assert [c["phrase_debut"] for c in res] == [10]


def test_parsing_indices_hors_transcription_ou_inverses():
    res = parser_candidats(rep(cand(95, 140), cand(30, 20), cand(-1, 5), cand(40, 50)), PHRASES)
    assert [c["phrase_debut"] for c in res] == [40]


def test_parsing_note_hors_plage_bornee():
    res = parser_candidats(rep(cand(1, 5, 140), cand(10, 15, -3)), PHRASES)
    assert [c["note"] for c in res] == [100, 0]


def test_parsing_note_non_numerique_ecartee():
    res = parser_candidats(rep(cand(1, 5, "excellent"), cand(10, 15, "72")), PHRASES)
    assert [c["note"] for c in res] == [72]


def test_parsing_indices_limites_au_bloc():
    bloc = PHRASES[50:]
    res = parser_candidats(rep(cand(10, 20), cand(60, 70)), bloc)
    assert [c["phrase_debut"] for c in res] == [60]


# --- Chevauchement et fusion ----------------------------------------------

def c(debut, fin, note=80):
    return {"debut_llm": debut, "fin_llm": fin, "note": note}


def test_chevauchement():
    assert chevauchement(c(0, 100), c(100, 200)) == 0
    assert chevauchement(c(0, 100), c(50, 250)) == pytest.approx(0.5)
    assert chevauchement(c(0, 300), c(100, 200)) == 1  # inclus


def test_fusion_garde_la_meilleure_note():
    res = fusionner([c(0, 200, 70), c(50, 250, 90)], 0.20, 15)
    assert [x["note"] for x in res] == [90]


def test_fusion_accepte_un_petit_chevauchement():
    res = fusionner([c(0, 200, 70), c(180, 380, 90)], 0.20, 15)  # 20 s sur 200 s = 10 %
    assert len(res) == 2
    assert [x["debut_llm"] for x in res] == [0, 180]  # trié par position


def test_fusion_seuil_strict():
    res = fusionner([c(0, 200, 70), c(160, 360, 90)], 0.20, 15)  # exactement 20 % : refusé
    assert len(res) == 1


def test_fusion_limite_nb_max():
    candidats = [c(i * 300, i * 300 + 200, note=i) for i in range(30)]
    res = fusionner(candidats, 0.20, 15)
    assert len(res) == 15
    assert min(x["note"] for x in res) == 15


def test_doublons_de_blocs_fusionnes():
    # Le même extrait vu par deux blocs qui se recouvrent ne sort qu'une fois.
    res = fusionner([c(3500, 3700, 82), c(3501, 3699, 80)], 0.20, 15)
    assert len(res) == 1 and res[0]["note"] == 82


# --- Blocs -----------------------------------------------------------------

def test_un_seul_bloc_si_court():
    assert len(blocs(PHRASES, 3600, 300)) == 1


def test_blocs_qui_se_recouvrent():
    longues = faire_phrases(800)  # ~2 h 20
    decoupe = blocs(longues, 3600, 300)
    assert len(decoupe) == 3
    for a, b in zip(decoupe, decoupe[1:]):
        recouvrement = a[-1].fin - b[0].debut
        assert 250 <= recouvrement <= 320
    couverts = {p.index for bloc in decoupe for p in bloc}
    assert couverts == {p.index for p in longues}


def test_remplir_ne_touche_pas_aux_autres_accolades():
    assert remplir("{{titre}} {json} {{x}}", titre="T") == "T {json} {{x}}"
