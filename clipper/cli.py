"""Interface en ligne de commande : clipper add | run | review | publish | status | stats."""

import argparse
import sys

from . import config as config_mod
from . import db, ingest, journal
from .journal import log
from .pipeline import Pipeline, verrou
from .transcript import hms

LIBELLES_ETAT = {
    "en_attente": "en attente",
    "telecharge": "téléchargée",
    "transcrit": "transcrite",
    "selectionne": "à revoir",
    "ignoree": "ignorée (trop courte)",
}


def cmd_add(cfg, cnx, args) -> int:
    log().info("Analyse de %s…", args.url)
    trouvees = ingest.developper_url(cfg, args.url)
    nouvelles = sum(db.ajouter_video(cnx, v["youtube_id"], v["url"], v["titre"], v["duree"]) for v in trouvees)
    log().info("%d vidéo(s) trouvée(s) : %d ajoutée(s), %d déjà présente(s)",
               len(trouvees), nouvelles, len(trouvees) - nouvelles)
    return 0


def cmd_run(cfg, cnx, args) -> int:
    with verrou(cfg):
        ok, echecs = Pipeline(cfg, cnx).executer(forcer=args.forcer)
    log().info("Terminé : %d vidéo(s) traitée(s), %d en échec", ok, echecs)
    return 1 if echecs else 0


def cmd_status(cfg, cnx, args) -> int:
    if args.video:
        return _detail_video(cnx, args.video)
    lignes = db.videos(cnx)
    if not lignes:
        print("Aucune vidéo. Commence par : clipper add URL")
        return 0
    print(f"{'#':>3}  {'Vidéo':<48} {'État':<22} {'Clips':>5} {'Coût':>8}")
    for v in lignes:
        nb = cnx.execute("SELECT COUNT(*) FROM clips WHERE video_id = ? AND etat != 'rejete_auto'",
                         (v["id"],)).fetchone()[0]
        titre = (v["titre"] or v["url"])[:48]
        etat = LIBELLES_ETAT.get(v["etat"], v["etat"])
        if v["erreur"]:
            etat = f"erreur ({v['tentatives']}×)"
        print(f"{v['id']:>3}  {titre:<48} {etat:<22} {nb:>5} {db.cout_video(cnx, v['id']):>7.3f}$")
        if v["erreur"]:
            print(f"     ↳ {v['erreur'][:110]}")
    print(f"\nCoût cumulé estimé : {db.cout_total(cnx):.3f} $")
    return 0


def _detail_video(cnx, video_id: int) -> int:
    v = db.video(cnx, video_id)
    if v is None:
        print(f"Vidéo #{video_id} introuvable")
        return 1
    print(f"#{v['id']} {v['titre']}  ({hms(v['duree'] or 0)}, {v['chaine'] or '?'})")
    print(f"Coût : {db.cout_video(cnx, v['id']):.3f} $\n")
    for c in db.clips(cnx, video_id):
        duree = c["fin"] - c["debut"]
        print(f"  [{c['note']:>3}/100] {hms(c['debut'])} → {hms(c['fin'])}  ({duree / 60:.1f} min)  {c['etat']}")
        print(f"          {c['sujet']}")
        print(f"          ↳ {c['raison']}")
    return 0


def cmd_a_venir(phase: int):
    def commande(cfg, cnx, args) -> int:
        print(f"Cette commande arrive en phase {phase}.")
        return 0
    return commande


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="clipper", description="Extraits YouTube de 2 à 5 minutes.")
    p.add_argument("--config", help="chemin de config.yaml (défaut : ./config.yaml)")
    p.add_argument("-v", "--verbeux", action="store_true", help="journal détaillé")
    sous = p.add_subparsers(dest="commande", required=True)

    s = sous.add_parser("add", help="ajouter une vidéo, une playlist ou une chaîne")
    s.add_argument("url")
    s.set_defaults(fonction=cmd_add)

    s = sous.add_parser("run", help="traiter les vidéos en attente (reprend après un crash)")
    s.add_argument("--forcer", action="store_true", help="relancer aussi les vidéos abandonnées")
    s.set_defaults(fonction=cmd_run)

    s = sous.add_parser("status", help="état des vidéos et coûts")
    s.add_argument("video", nargs="?", type=int, help="numéro de vidéo pour voir ses clips")
    s.set_defaults(fonction=cmd_status)

    sous.add_parser("review", help="page de revue locale").set_defaults(fonction=cmd_a_venir(2))
    sous.add_parser("publish", help="publier la file sur YouTube").set_defaults(fonction=cmd_a_venir(3))
    sous.add_parser("stats", help="suivi des clips publiés").set_defaults(fonction=cmd_a_venir(4))

    args = p.parse_args(argv)
    try:
        cfg = config_mod.charger(args.config)
    except config_mod.ErreurConfig as e:
        print(f"Erreur : {e}", file=sys.stderr)
        return 2
    journal.configurer(cfg.dossier_donnees, args.verbeux)
    cnx = db.connecter(cfg.chemin_db)
    try:
        return args.fonction(cfg, cnx, args)
    except config_mod.ErreurConfig as e:
        log().error("%s", e)
        return 2
    except KeyboardInterrupt:
        log().warning("Interrompu : relance la même commande pour reprendre.")
        return 130
    finally:
        cnx.close()


if __name__ == "__main__":
    sys.exit(main())
