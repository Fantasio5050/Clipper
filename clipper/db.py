"""État persistant dans SQLite. Le schéma évolue par migrations numérotées."""

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

# Chaque entrée est appliquée une seule fois, dans l'ordre (PRAGMA user_version).
MIGRATIONS = [
    """
    CREATE TABLE videos (
        id            INTEGER PRIMARY KEY,
        youtube_id    TEXT NOT NULL UNIQUE,
        url           TEXT NOT NULL,
        titre         TEXT,
        chaine        TEXT,
        duree         REAL,
        chemin_video  TEXT,
        etat          TEXT NOT NULL DEFAULT 'en_attente',
        erreur        TEXT,
        tentatives    INTEGER NOT NULL DEFAULT 0,
        ajoute_le     TEXT NOT NULL,
        maj_le        TEXT NOT NULL
    );
    CREATE TABLE clips (
        id              INTEGER PRIMARY KEY,
        video_id        INTEGER NOT NULL REFERENCES videos(id),
        debut           REAL NOT NULL,
        fin             REAL NOT NULL,
        debut_llm       REAL NOT NULL,
        fin_llm         REAL NOT NULL,
        sujet           TEXT NOT NULL,
        note            INTEGER NOT NULL,
        raison          TEXT NOT NULL,
        etat            TEXT NOT NULL DEFAULT 'candidat',
        motif_rejet     TEXT,
        cree_le         TEXT NOT NULL,
        maj_le          TEXT NOT NULL
    );
    CREATE INDEX clips_video ON clips(video_id);
    CREATE TABLE couts (
        id        INTEGER PRIMARY KEY,
        video_id  INTEGER REFERENCES videos(id),
        poste     TEXT NOT NULL,
        quantite  REAL NOT NULL,
        unite     TEXT NOT NULL,
        montant   REAL NOT NULL,
        cree_le   TEXT NOT NULL
    );
    """,
]


def maintenant() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connecter(chemin: Path) -> sqlite3.Connection:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    cnx = sqlite3.connect(chemin, isolation_level=None, timeout=30)
    cnx.row_factory = sqlite3.Row
    cnx.execute("PRAGMA journal_mode=WAL")
    cnx.execute("PRAGMA foreign_keys=ON")
    migrer(cnx)
    return cnx


def migrer(cnx: sqlite3.Connection) -> None:
    version = cnx.execute("PRAGMA user_version").fetchone()[0]
    for numero, script in enumerate(MIGRATIONS[version:], start=version + 1):
        with transaction(cnx):
            for instruction in script.split(";"):
                if instruction.strip():
                    cnx.execute(instruction)
            cnx.execute(f"PRAGMA user_version = {numero}")


@contextmanager
def transaction(cnx: sqlite3.Connection):
    """Bloc atomique : tout est écrit, ou rien en cas d'exception (reprise après crash)."""
    cnx.execute("BEGIN IMMEDIATE")
    try:
        yield cnx
    except BaseException:
        cnx.execute("ROLLBACK")
        raise
    cnx.execute("COMMIT")


# --- Vidéos ---------------------------------------------------------------

def ajouter_video(cnx, youtube_id: str, url: str, titre: str | None = None, duree: float | None = None) -> bool:
    """Ajoute une vidéo. Renvoie False si elle existe déjà (aucun doublon possible)."""
    t = maintenant()
    cur = cnx.execute(
        "INSERT OR IGNORE INTO videos (youtube_id, url, titre, duree, ajoute_le, maj_le) VALUES (?, ?, ?, ?, ?, ?)",
        (youtube_id, url, titre, duree, t, t),
    )
    return cur.rowcount == 1


def maj_video(cnx, video_id: int, **champs) -> None:
    champs["maj_le"] = maintenant()
    cles = ", ".join(f"{k} = ?" for k in champs)
    cnx.execute(f"UPDATE videos SET {cles} WHERE id = ?", (*champs.values(), video_id))


def video(cnx, video_id: int):
    return cnx.execute("SELECT * FROM videos WHERE id = ?", (video_id,)).fetchone()


def videos(cnx):
    return cnx.execute("SELECT * FROM videos ORDER BY id").fetchall()


# --- Clips ----------------------------------------------------------------

def remplacer_candidats(cnx, video_id: int, candidats: list[dict]) -> None:
    """Enregistre les candidats d'une vidéo (à appeler dans une transaction)."""
    cnx.execute("DELETE FROM clips WHERE video_id = ? AND etat IN ('candidat', 'rejete_auto')", (video_id,))
    t = maintenant()
    for c in candidats:
        cnx.execute(
            """INSERT INTO clips (video_id, debut, fin, debut_llm, fin_llm, sujet, note, raison,
                                  etat, motif_rejet, cree_le, maj_le)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (video_id, c["debut"], c["fin"], c["debut_llm"], c["fin_llm"], c["sujet"], c["note"],
             c["raison"], c.get("etat", "candidat"), c.get("motif_rejet"), t, t),
        )


def clips(cnx, video_id: int):
    return cnx.execute("SELECT * FROM clips WHERE video_id = ? ORDER BY debut", (video_id,)).fetchall()


# --- Coûts ----------------------------------------------------------------

def ajouter_cout(cnx, video_id: int | None, poste: str, quantite: float, unite: str, montant: float) -> None:
    cnx.execute(
        "INSERT INTO couts (video_id, poste, quantite, unite, montant, cree_le) VALUES (?, ?, ?, ?, ?, ?)",
        (video_id, poste, quantite, unite, montant, maintenant()),
    )


def cout_video(cnx, video_id: int) -> float:
    return cnx.execute("SELECT COALESCE(SUM(montant), 0) FROM couts WHERE video_id = ?", (video_id,)).fetchone()[0]


def cout_total(cnx) -> float:
    return cnx.execute("SELECT COALESCE(SUM(montant), 0) FROM couts").fetchone()[0]
