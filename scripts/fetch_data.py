#!/usr/bin/env python3
"""
Collecte périodique des données publiques d'Empire Immo, pour TOUS les mondes
listés dans config/worlds.json.

config/worlds.json est maintenu manuellement (par l'utilisateur du repo, pas
par ce script) car la liste des mondes change rarement. Format attendu :

{
  "mondes": [
    {
      "id": "monde8",
      "nom": "Monde 8",
      "buildings_url": "https://monde8.empireimmo.com/api/buildings.json",
      "materials_url": "https://monde8.empireimmo.com/api/materials.json"
    },
    ...
  ]
}

Pour chaque monde, buildings_url et materials_url sont interrogées
indépendamment (jamais players_url, même si elle existe : pas de suivi de
joueurs demandé). L'échec d'une source, sur un monde, n'empêche jamais la
collecte des autres sources/mondes.

Pour chaque (monde, source) qui réussit, une ligne JSONL est ajoutée à
data/history/<monde_id>/<source>.jsonl au format :
    {"fetched_at": "<ISO8601 UTC>", "source_mise_a_jour": <valeur ou null>, "data": {...}}

Code de sortie :
    0 si au moins un (monde, source) a réussi
    1 si tout a échoué, ou si config/worlds.json est absent/invalide
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

TIMEOUT_SECONDS = 20

# Clés d'URL à interroger pour chaque monde (jamais "players_url").
SOURCE_URL_KEYS = {
    "buildings": "buildings_url",
    "materials": "materials_url",
}

MISE_A_JOUR_KEYS = (
    "mise_a_jour",
    "maj",
    "updated_at",
    "last_update",
    "last_updated",
    "date_maj",
)

ROOT_DIR = Path(__file__).resolve().parent.parent
WORLDS_CONFIG_PATH = ROOT_DIR / "config" / "worlds.json"
HISTORY_DIR = ROOT_DIR / "data" / "history"


def load_worlds() -> list[dict]:
    """Charge la liste des mondes depuis config/worlds.json.

    Ce fichier est maintenu à la main ; on reste donc défensif sur son
    contenu (champs manquants, monde mal formé...) plutôt que de planter.
    """
    if not WORLDS_CONFIG_PATH.exists():
        print(f"[fetch_data] ERREUR : {WORLDS_CONFIG_PATH} introuvable.", file=sys.stderr)
        return []

    try:
        raw = json.loads(WORLDS_CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[fetch_data] ERREUR lecture {WORLDS_CONFIG_PATH} : {exc}", file=sys.stderr)
        return []

    mondes = raw.get("mondes", []) if isinstance(raw, dict) else []
    valides = []
    for monde in mondes:
        if not isinstance(monde, dict):
            continue
        monde_id = monde.get("id")
        if not monde_id:
            print(f"[fetch_data] Monde sans 'id' ignoré : {monde}", file=sys.stderr)
            continue
        valides.append(monde)
    return valides


def _extract_source_mise_a_jour(payload: object) -> object | None:
    if not isinstance(payload, dict):
        return None
    for key in MISE_A_JOUR_KEYS:
        if key in payload:
            return payload[key]
    return None


def fetch_url(url: str) -> dict | None:
    try:
        response = requests.get(url, timeout=TIMEOUT_SECONDS)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        print(f"[fetch_data] ÉCHEC requête '{url}' : {exc}", file=sys.stderr)
        return None
    except ValueError as exc:
        print(f"[fetch_data] ÉCHEC décodage JSON '{url}' : {exc}", file=sys.stderr)
        return None


def append_jsonl(monde_id: str, source: str, payload: dict, fetched_at: str) -> None:
    monde_dir = HISTORY_DIR / monde_id
    monde_dir.mkdir(parents=True, exist_ok=True)
    line = {
        "fetched_at": fetched_at,
        "source_mise_a_jour": _extract_source_mise_a_jour(payload),
        "data": payload,
    }
    target = monde_dir / f"{source}.jsonl"
    with target.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(line, ensure_ascii=False))
        fh.write("\n")


def main() -> int:
    worlds = load_worlds()
    if not worlds:
        print(
            "[fetch_data] Aucun monde valide dans config/worlds.json — rien à collecter.",
            file=sys.stderr,
        )
        return 1

    fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    success_count = 0
    total_count = 0

    for monde in worlds:
        monde_id = monde["id"]
        monde_nom = monde.get("nom", monde_id)

        for source, url_key in SOURCE_URL_KEYS.items():
            url = monde.get(url_key)
            if not url:
                print(
                    f"[fetch_data] Monde '{monde_nom}' : '{url_key}' absent, source '{source}' ignorée.",
                    file=sys.stderr,
                )
                continue

            total_count += 1
            payload = fetch_url(url)
            if payload is None:
                continue

            try:
                append_jsonl(monde_id, source, payload, fetched_at)
                success_count += 1
                print(f"[fetch_data] OK '{monde_nom}'/'{source}' écrit ({fetched_at}).")
            except OSError as exc:
                print(f"[fetch_data] ÉCHEC écriture '{monde_nom}'/'{source}' : {exc}", file=sys.stderr)

    if success_count == 0:
        print("[fetch_data] Aucune source n'a pu être collectée, pour aucun monde.", file=sys.stderr)
        return 1

    print(f"[fetch_data] {success_count}/{total_count} collecte(s) réussie(s) sur {len(worlds)} monde(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
