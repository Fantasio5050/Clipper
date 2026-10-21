"""Sélection des extraits candidats par Claude : blocs, parsing, fusion, chevauchement."""

import math

from . import db, transcribe
from .config import Config
from .journal import log
from .llm import ClientLLM, ErreurLLM, extraire_json
from .transcript import Phrase, hms, mots_deepgram, phrases, texte_pour_llm

SCHEMA = {
    "type": "object",
    "properties": {
        "candidats": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "phrase_debut": {"type": "integer"},
                    "phrase_fin": {"type": "integer"},
                    "sujet": {"type": "string"},
                    "note": {"type": "integer"},
                    "raison": {"type": "string"},
                },
                "required": ["phrase_debut", "phrase_fin", "sujet", "note", "raison"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["candidats"],
    "additionalProperties": False,
}


def remplir(modele: str, **valeurs) -> str:
    """Remplace les {{variables}} d'un prompt (les autres accolades restent intactes)."""
    for cle, valeur in valeurs.items():
        modele = modele.replace("{{" + cle + "}}", str(valeur))
    return modele


def _minutes(secondes: float) -> str:
    return f"{secondes / 60:g}".replace(".", ",")


def blocs(liste: list[Phrase], bloc_s: float, recouvrement_s: float) -> list[list[Phrase]]:
    """Découpe en blocs de bloc_s secondes qui se recouvrent de recouvrement_s secondes."""
    if not liste or liste[-1].fin - liste[0].debut <= bloc_s:
        return [liste] if liste else []
    resultat = []
    debut = liste[0].debut
    pas = bloc_s - recouvrement_s
    while True:
        fin = debut + bloc_s
        bloc = [p for p in liste if p.debut >= debut and p.debut < fin]
        if bloc:
            resultat.append(bloc)
        if fin >= liste[-1].fin:
            return resultat
        debut += pas


def parser_candidats(texte: str, liste: list[Phrase]) -> list[dict]:
    """Valide la réponse de Claude. Les candidats invalides sont écartés avec un avertissement."""
    donnees = extraire_json(texte)
    bruts = donnees.get("candidats") if isinstance(donnees, dict) else None
    if not isinstance(bruts, list):
        raise ErreurLLM("La réponse de Claude n'a pas de liste « candidats »")

    par_index = {p.index: p for p in liste}
    valides = []
    for n, c in enumerate(bruts, 1):
        try:
            i0, i1 = int(c["phrase_debut"]), int(c["phrase_fin"])
            note = int(c["note"])
            sujet, raison = str(c["sujet"]).strip(), str(c["raison"]).strip()
        except (KeyError, TypeError, ValueError) as e:
            log().warning("Candidat %d ignoré : champ manquant ou invalide (%s)", n, e)
            continue
        if i0 not in par_index or i1 not in par_index or i1 < i0:
            log().warning("Candidat %d ignoré : phrases #%s à #%s hors transcription", n, i0, i1)
            continue
        if not sujet:
            log().warning("Candidat %d ignoré : sujet vide", n)
            continue
        valides.append({
            "phrase_debut": i0, "phrase_fin": i1,
            "debut_llm": par_index[i0].debut, "fin_llm": par_index[i1].fin,
            "sujet": sujet, "note": max(0, min(100, note)), "raison": raison,
        })
    return valides


def chevauchement(a: dict, b: dict) -> float:
    """Part du clip le plus court couverte par l'autre (0 = disjoints, 1 = inclus)."""
    inter = min(a["fin_llm"], b["fin_llm"]) - max(a["debut_llm"], b["debut_llm"])
    plus_court = min(a["fin_llm"] - a["debut_llm"], b["fin_llm"] - b["debut_llm"])
    if inter <= 0 or plus_court <= 0:
        return 0.0
    return inter / plus_court


def fusionner(candidats: list[dict], chevauchement_max: float, nb_max: int) -> list[dict]:
    """Garde les meilleures notes en écartant les chevauchements, puis trie par position."""
    gardes: list[dict] = []
    for c in sorted(candidats, key=lambda c: -c["note"]):
        if len(gardes) >= nb_max:
            break
        if all(chevauchement(c, g) < chevauchement_max for g in gardes):
            gardes.append(c)
    return sorted(gardes, key=lambda c: c["debut_llm"])


def selectionner(cfg: Config, cnx, video, client: ClientLLM) -> list[dict]:
    sel = cfg["selection"]
    liste = phrases(mots_deepgram(transcribe.charger(cfg, video["youtube_id"])))
    if not liste:
        raise RuntimeError("Transcription vide : aucun mot reconnu")
    decoupe = blocs(liste, sel["bloc_min"] * 60, sel["recouvrement_min"] * 60)
    modele_prompt = cfg.prompt("selection")

    candidats = []
    for n, bloc in enumerate(decoupe, 1):
        if len(decoupe) == 1:
            portee = "La transcription ci-dessous couvre toute la vidéo."
            nb_min, nb_max = sel["nb_min"], sel["nb_max"]
        else:
            portee = (f"La transcription ci-dessous est le bloc {n}/{len(decoupe)} de la vidéo, "
                      f"de {hms(bloc[0].debut)} à {hms(bloc[-1].fin)}. Ignore les extraits coupés par les bords du bloc.")
            part = (bloc[-1].fin - bloc[0].debut) / (liste[-1].fin - liste[0].debut)
            nb_min, nb_max = 2, max(3, math.ceil(sel["nb_max"] * part) + 2)
        systeme = remplir(
            modele_prompt, titre=video["titre"] or "inconnu", chaine=video["chaine"] or "inconnue",
            duree=hms(video["duree"] or liste[-1].fin), portee=portee, nb_min=nb_min, nb_max=nb_max,
            duree_min=_minutes(sel["duree_min_s"]), duree_max=_minutes(sel["duree_max_s"]) + " minutes",
        )
        log().info("[%s] Sélection par Claude, bloc %d/%d (%d phrases)", video["youtube_id"], n, len(decoupe), len(bloc))
        texte = client.json(
            modele=sel["modele"], systeme=systeme, contenu=texte_pour_llm(bloc), schema=SCHEMA,
            effort=sel["effort"], video_id=video["id"], poste="selection",
        )
        trouves = parser_candidats(texte, bloc)
        log().info("[%s] Bloc %d : %d candidats valides", video["youtube_id"], n, len(trouves))
        candidats.extend(trouves)

    retenus = fusionner(candidats, sel["chevauchement_max"], sel["nb_max"])
    if len(retenus) < sel["nb_min"]:
        log().warning("[%s] Seulement %d candidats retenus (minimum visé : %d)",
                      video["youtube_id"], len(retenus), sel["nb_min"])
    with db.transaction(cnx):
        db.remplacer_candidats(cnx, video["id"], [{**c, "debut": c["debut_llm"], "fin": c["fin_llm"]} for c in retenus])
        db.maj_video(cnx, video["id"], etat="selectionne")
    log().info("[%s] %d candidats enregistrés", video["youtube_id"], len(retenus))
    return retenus
