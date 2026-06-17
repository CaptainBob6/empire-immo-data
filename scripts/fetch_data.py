#!/usr/bin/env python3
"""Récupère les APIs publiques d'Empire Immo (Monde 8) et ajoute un snapshot
horodaté à un fichier JSONL d'historique.

Conçu pour être lancé périodiquement par GitHub Actions (cron), mais peut
aussi être lancé à la main : `python scripts/fetch_data.py`.

Chaque exécution réussie ajoute UNE ligne par source à
data/history/<source>.jsonl, au format :
    {"fetched_at": "2026-06-17T12:00:03+00:00", "source_mise_a_jour": "...", "data": {...}}

Les sources sont traitées indépendamment : si l'une échoue (site indisponible,
timeout...), les autres sont quand même sauvegardées.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

ENDPOINTS = {
    "buildings": "https://monde8.empireimmo.com/api/buildings.json",
    "materials": "https://monde8.empireimmo.com/api/materials.json",
}

ROOT = Path(__file__).resolve().parent.parent
HISTORY_DIR = ROOT / "data" / "history"
TIMEOUT_SECONDS = 20


def fetch_one(name: str, url: str) -> bool:
    history_file = HISTORY_DIR / f"{name}.jsonl"
    history_file.parent.mkdir(parents=True, exist_ok=True)

    try:
        response = requests.get(url, timeout=TIMEOUT_SECONDS)
        response.raise_for_status()
        data = response.json()
    except Exception as exc:  # noqa: BLE001 - on continue avec les autres sources
        print(f"[ERREUR] {name}: {exc}", file=sys.stderr)
        return False

    record = {
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_mise_a_jour": data.get("mise_a_jour"),
        "data": data,
    }

    with history_file.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(f"[OK] {name}: snapshot ajouté à {history_file.relative_to(ROOT)} ({record['fetched_at']})")
    return True


def main() -> int:
    results = [fetch_one(name, url) for name, url in ENDPOINTS.items()]
    # On considère l'exécution comme un échec uniquement si AUCUNE source n'a pu être récupérée.
    return 0 if any(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
