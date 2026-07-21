"""Rebuild game_brain/game_kb.db from committed sources.

The SQLite DB is gitignored (a build artifact); this regenerates it from the
committed JSONL sources so anyone can reconstruct the knowledge base:
  data/generals.jsonl        -> generals + ratings
  data/site_guides.jsonl     -> raw guide pages (bulk ingest, 1 line per page)
  data/guides/*.jsonl        -> higher-quality per-category summaries (overlaid last)

  python rebuild_kb.py
"""

import glob
import json
import os

import game_kb


def rebuild(db_path="game_brain/game_kb.db"):
    db = game_kb.GameKB(db_path)
    n_gen = db.load_generals_jsonl("data/generals.jsonl") if os.path.exists("data/generals.jsonl") else 0
    # site_guides first (raw), then category files last so their better summaries win on dedup(url)
    sources = (["data/site_guides.jsonl"] if os.path.exists("data/site_guides.jsonl") else []) + \
              sorted(glob.glob("data/guides/*.jsonl"))
    n_guide = 0
    for f in sources:
        for line in open(f):
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get("url"):
                db.add_guide(r.get("title"), r["url"], r.get("category"), r.get("summary"), r.get("content"))
                n_guide += 1
    return {"generals": n_gen, "guides_loaded": n_guide, "stats": db.stats()}


if __name__ == "__main__":
    print(rebuild())
