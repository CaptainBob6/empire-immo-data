#!/usr/bin/env python3
"""
fetch_data.py — Récupère les données publiques d'Empire Immo pour chaque
monde déclaré dans config/worlds.json, et ajoute (append) les relevés aux
fichiers JSONL d'historique correspondants.

Mondes : définis manuellement par l'utilisateur dans config/worlds.json,
à la racine du dépôt (un id + un nom + une base_url par monde). Ce script
ne doit jamais être modifié pour ajouter un monde — il suffit d'éditer ce
fichier de config.

Chaque (monde, source) est traité indépendamment : l'échec de l'un n'empêche
jamais les autres de continuer (réseau capricieux, monde temporairement down...).

Fichier produit : data/history/<world_id>/<source>.jsonl, une ligne par relevé :
{"fetched_at": "<ISO8601 UTC>", "source_mise_a_jour": <valeur ou null>, "data": {...}}

⚠️ players.json existe mais n'est volontairement jamais interrogé ici
   (pas de suivi de joueurs demandé).

Code de sortie :
  0 si au moins un (monde, source) a été récupéré avec succès
  1 si tout a échoué
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
WORLDS_CONFIG = ROOT / "config" / "worlds.json"
HISTORY_DIR = ROOT / "data" / "history"
TIMEOUT = 20

# Sources interrogées pour chaque monde (players.json est exclu volontairement).
SOURCES = ("buildings", "materials")


def load_worlds() -> list[dict]:
    if not WORLDS_CONFIG.exists():
        print(f"⚠️  Fichier de configuration introuvable : {WORLDS_CONFIG}", file=sys.stderr)
        return []
    try:
        worlds = json.loads(WORLDS_CONFIG.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"⚠️  config/worlds.json invalide (JSON mal formé) : {e}", file=sys.stderr)
        return []

    valid = []
    for w in worlds:
        if isinstance(w, dict) and w.get("id") and w.get("base_url"):
            valid.append(w)
        else:
            print(f"⚠️  Entrée de monde ignorée (id ou base_url manquant) : {w}", file=sys.stderr)
    return valid


def fetch_source(base_url: str, source: str) -> dict:
    url = base_url.rstrip("/") + f"/{source}.json"
    resp = requests.get(url, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def append_jsonl(world_id: str, source: str, payload) -> None:
    world_dir = HISTORY_DIR / world_id
    world_dir.mkdir(parents=True, exist_ok=True)
    out_path = world_dir / f"{source}.jsonl"

    source_maj = payload.get("mise_a_jour") if isinstance(payload, dict) else None
    record = {
        "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_mise_a_jour": source_maj,
        "data": payload,
    }
    with out_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def main() -> int:
    worlds = load_worlds()
    if not worlds:
        print("❌ Aucun monde valide déclaré dans config/worlds.json — rien à faire.", file=sys.stderr)
        return 1

    any_success = False
    for world in worlds:
        world_id = world["id"]
        nom = world.get("nom", world_id)
        base_url = world["base_url"]

        for source in SOURCES:
            try:
                payload = fetch_source(base_url, source)
                append_jsonl(world_id, source, payload)
                print(f"✅ {nom} ({world_id}) — {source}.json récupéré et ajouté à l'historique.")
                any_success = True
            except Exception as e:  # noqa: BLE001 — on isole volontairement chaque échec
                print(f"❌ {nom} ({world_id}) — {source}.json a échoué : {e}", file=sys.stderr)

    if not any_success:
        print("❌ Tous les relevés ont échoué.", file=sys.stderr)
    return 0 if any_success else 1


if __name__ == "__main__":
    sys.exit(main())
