from clipper.transcript import hms, mots_deepgram, phrases, texte_pour_llm


def m(mot, debut, fin, loc=0):
    return {"mot": mot, "debut": debut, "fin": fin, "locuteur": loc}


def test_coupure_sur_ponctuation_et_locuteur():
    mots = [m("Bonjour", 0, 0.4), m("à", 0.5, 0.6), m("tous.", 0.6, 1.0),
            m("Merci", 1.2, 1.5, 1), m("beaucoup", 1.5, 1.9, 1), m("alors", 2.0, 2.3, 0)]
    res = phrases(mots)
    assert [p.texte for p in res] == ["Bonjour à tous.", "Merci beaucoup", "alors"]
    assert [p.locuteur for p in res] == [0, 1, 0]
    assert (res[0].debut, res[0].fin) == (0, 1.0)
    assert [p.index for p in res] == [0, 1, 2]


def test_coupure_sur_longue_pause():
    res = phrases([m("et", 0, 0.2), m("puis", 0.3, 0.5), m("ensuite", 3.0, 3.4)])
    assert len(res) == 2


def test_mots_deepgram():
    brut = {"results": {"channels": [{"alternatives": [{"words": [
        {"word": "salut", "punctuated_word": "Salut,", "start": 0.1, "end": 0.4, "speaker": 1},
        {"word": "toi", "start": 0.5, "end": 0.7},
    ]}]}]}}
    assert mots_deepgram(brut) == [m("Salut,", 0.1, 0.4, 1), m("toi", 0.5, 0.7, 0)]


def test_texte_pour_llm():
    res = phrases([m("Oui.", 3725.2, 3725.6, 1)])
    assert texte_pour_llm(res) == "#0 [01:02:05] L2: Oui."
    assert hms(59.9) == "00:00:59"
