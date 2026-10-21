"""Appels à Claude avec sortie JSON structurée, et enregistrement du coût."""

import json

import anthropic

from . import db
from .config import Config
from .journal import log


class ErreurLLM(Exception):
    pass


class ClientLLM:
    def __init__(self, cfg: Config, cnx):
        self.cfg = cfg
        self.cnx = cnx
        conf = cfg["anthropic"]
        self.client = anthropic.Anthropic(api_key=cfg.cle("ANTHROPIC_API_KEY"), base_url=conf["base_url"])
        self.repli = conf.get("repli_sur_refus", True)

    def json(self, *, modele: str, systeme: str, contenu: str, schema: dict, effort: str,
             video_id: int | None, poste: str, max_tokens: int = 16000) -> str:
        """Envoie la requête et renvoie le texte JSON brut de la réponse (parsé par l'appelant)."""
        options = {}
        if self.repli:
            # En cas de refus, l'API relance elle-même la requête sur un modèle de repli.
            options = {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}
        with self.client.beta.messages.stream(
            model=modele,
            max_tokens=max_tokens,
            system=systeme,
            messages=[{"role": "user", "content": contenu}],
            output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
            **options,
        ) as flux:
            reponse = flux.get_final_message()

        self._enregistrer_cout(reponse, modele, video_id, poste)
        if reponse.stop_reason == "refusal":
            raise ErreurLLM(f"Claude a refusé la requête ({poste})")
        if reponse.stop_reason == "max_tokens":
            raise ErreurLLM(f"Réponse tronquée ({poste}) : augmenter max_tokens")
        return "".join(b.text for b in reponse.content if b.type == "text")

    def _enregistrer_cout(self, reponse, modele: str, video_id, poste: str) -> None:
        u = reponse.usage
        entree = (u.input_tokens or 0) + (u.cache_creation_input_tokens or 0) + (u.cache_read_input_tokens or 0)
        sortie = u.output_tokens or 0
        tarif = self.cfg["anthropic"]["tarifs"].get(modele)
        if tarif is None:
            log().warning("Pas de tarif pour %s dans config.yaml : coût compté à 0", modele)
            montant = 0.0
        else:
            montant = (entree * tarif["entree"] + sortie * tarif["sortie"]) / 1_000_000
        db.ajouter_cout(self.cnx, video_id, poste, entree + sortie, "jetons", montant)
        log().info("Claude (%s) : %d jetons en entrée, %d en sortie, ~%.3f $", poste, entree, sortie, montant)


def extraire_json(texte: str):
    """Récupère l'objet JSON d'une réponse, même entouré de texte ou de balises ```json."""
    texte = texte.strip()
    try:
        return json.loads(texte)
    except json.JSONDecodeError:
        pass
    debut = texte.find("{")
    fin = texte.rfind("}")
    if debut == -1 or fin <= debut:
        raise ErreurLLM("Aucun objet JSON dans la réponse de Claude")
    try:
        return json.loads(texte[debut:fin + 1])
    except json.JSONDecodeError as e:
        raise ErreurLLM(f"JSON invalide dans la réponse de Claude : {e}") from None
