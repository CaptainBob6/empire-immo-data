#!/usr/bin/env python3
"""
Synchronise data/history/{world_id}/players.json pour chaque monde déclaré dans
config/worlds.json — en ÉCRASANT le fichier à chaque exécution (pas d'historique
qui grossit, contrairement à buildings.jsonl / materials.jsonl).

Pour chaque monde, ce script lit l'URL de son API joueurs depuis la clé
"players_api_url" de son entrée dans config/worlds.json, par exemple :

    {
      "id": "m8",
      "nom": "Monde 8",
      "players_api_url": "https://monde8.empireimmo.com/api/players.json"
    }

Si cette clé est absente ou vide pour un monde, ce monde est simplement ignoré
(avec un avertissement) — les autres mondes ne sont pas affectés.

Si la requête échoue ou que la réponse ne contient pas de tableau "joueurs"
valide, l'ancien fichier n'est PAS écrasé (on garde la dernière version connue
plutôt que de la remplacer par du vide en cas de panne temporaire de l'API).

Aucune dépendance externe : n'utilise que la bibliothèque standard Python 3
(déjà disponible sur les runners GitHub Actions ubuntu-latest).
"""

import json
import sys
import urllib.request
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORLDS_FILE = ROOT / "config" / "worlds.json"
HISTORY_DIR = ROOT / "data" / "history"

REQUEST_TIMEOUT_SECONDS = 20
USER_AGENT = "EmpireImmoSync/1.0"


def fetch_json(url: str) -> dict | None:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_SECONDS) as resp:
            status = getattr(resp, "status", None)
            if status not in (200, None):
                print(f"  ⚠️  HTTP {status} pour {url}")
                return None
            raw = resp.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
        print(f"  ⚠️  Erreur réseau sur {url} : {e}")
        return None

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"  ⚠️  Réponse JSON invalide depuis {url} : {e}")
        return None

    if not isinstance(data, dict) or not isinstance(data.get("joueurs"), list):
        print(f"  ⚠️  Réponse de {url} sans tableau 'joueurs' valide.")
        return None

    return data


def main() -> int:
    if not WORLDS_FILE.exists():
        print(f"❌ Fichier introuvable : {WORLDS_FILE}")
        return 1

    worlds = json.loads(WORLDS_FILE.read_text(encoding="utf-8"))
    if not isinstance(worlds, list):
        print("❌ config/worlds.json devrait contenir une liste de mondes.")
        return 1

    any_success = False
    any_failure = False

    for world in worlds:
        world_id = world.get("id")
        api_url = (world.get("players_api_url") or "").strip()
        nom = world.get("nom", world_id)

        if not world_id:
            continue
        if not api_url:
            print(f"⏭️  {nom} ({world_id}) : pas de players_api_url configurée, ignoré.")
            continue

        print(f"🔄 {nom} ({world_id}) : récupération depuis {api_url}")
        data = fetch_json(api_url)
        if data is None:
            print(f"  ❌ Échec — fichier players.json existant conservé tel quel pour ce monde.")
            any_failure = True
            continue

        world_dir = HISTORY_DIR / world_id
        world_dir.mkdir(parents=True, exist_ok=True)
        out_file = world_dir / "players.json"
        out_file.write_text(
            json.dumps(data, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        print(f"  ✅ {len(data['joueurs'])} joueur(s) écrits dans {out_file.relative_to(ROOT)}")
        any_success = True

    if not any_success and any_failure:
        # Aucun monde n'a pu être synchronisé cette fois : on le signale (code de sortie
        # non nul) sans pour autant supprimer quoi que ce soit — les anciens fichiers restent.
        print("⚠️  Aucune synchronisation joueurs n'a réussi cette exécution.")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
