"""Mots horodatés → phrases, et texte compact envoyé à Claude."""

from dataclasses import dataclass

FINS_DE_PHRASE = (".", "?", "!", "…")


@dataclass
class Phrase:
    index: int
    debut: float
    fin: float
    locuteur: int
    texte: str


def mots_deepgram(brut: dict) -> list[dict]:
    """Extrait [{mot, debut, fin, locuteur}] de la réponse brute de Deepgram."""
    alternative = brut["results"]["channels"][0]["alternatives"][0]
    return [
        {"mot": m.get("punctuated_word") or m["word"], "debut": m["start"], "fin": m["end"],
         "locuteur": m.get("speaker", 0)}
        for m in alternative.get("words", [])
    ]


def phrases(mots: list[dict], pause_max: float = 1.5) -> list[Phrase]:
    """Regroupe les mots en phrases : coupure sur ponctuation finale, changement de locuteur ou longue pause."""
    resultat: list[Phrase] = []
    courant: list[dict] = []

    def clore():
        if courant:
            resultat.append(Phrase(len(resultat), courant[0]["debut"], courant[-1]["fin"],
                                   courant[0]["locuteur"], " ".join(m["mot"] for m in courant)))
            courant.clear()

    for mot in mots:
        if courant and (mot["locuteur"] != courant[-1]["locuteur"] or mot["debut"] - courant[-1]["fin"] > pause_max):
            clore()
        courant.append(mot)
        if mot["mot"].endswith(FINS_DE_PHRASE):
            clore()
    clore()
    return resultat


def hms(secondes: float) -> str:
    s = int(secondes)
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def texte_pour_llm(liste: list[Phrase]) -> str:
    """Une ligne par phrase : « #12 [00:01:03] L1: texte ». Claude répond avec les numéros."""
    return "\n".join(f"#{p.index} [{hms(p.debut)}] L{p.locuteur + 1}: {p.texte}" for p in liste)
