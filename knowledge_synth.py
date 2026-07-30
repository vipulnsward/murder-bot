#!/usr/bin/env python3
"""knowledge_synth.py — the SELF-EVOLVING BRAIN: distill external Evony learning.

Pillar: "self evolving brain / learn all / watch YouTube + Discord + self-explore".
knowledge_ingest.py fills the Postgres `knowledge` table (db murderbot) with RAW
external content (YouTube transcripts, Discord messages). This module SYNTHESIZES that
raw text into concrete, deduped Evony TACTICS / RULES / NUMBERS that the brain and the
advisors (counter_ai, general_advisor) can CITE.

  synth()          read `knowledge`, extract concrete insights, and APPEND them to
                   game_brain/knowledge_distilled.md — every insight attributed to its
                   source video title and tagged `confidence: external-video`. It NEVER
                   blindly overwrites pvp_brain.md (the hand-verified doctrine); it only
                   appends new, deduped insights and prints a diff summary.
  relevant(q, k)   top-k external snippets for a live situation, TF/keyword ranked, so
                   counter_ai/advisors can quote what the community actually teaches.

Extraction is HEURISTIC by default (regex over Evony jargon + numbers) and works fully
offline with zero API cost. If MOONSHOT_API_KEY is set and reachable, an optional Kimi
pass (https://api.moonshot.cn/v1, kimi-k2-0711-preview, OpenAI-compatible) refines each
video's raw fragments into cleaner rules; it runs on a short timeout, NEVER blocks, and
falls back to the heuristic on any error.

  python knowledge_synth.py --synth            # distill the knowledge base (heuristic)
  python knowledge_synth.py --synth --no-llm   # force heuristic-only, offline
  python knowledge_synth.py --synth --llm      # force the Moonshot refinement pass
  python knowledge_synth.py --stats            # coverage of raw + distilled
  python knowledge_synth.py --query "counter a siege rally" -k 5   # test relevant()

Read-only w.r.t. the game (no ADB, never spends gems). Appends to a markdown file under
game_brain/; the authoritative pvp_brain.md is never touched.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import sys
from pathlib import Path

try:
    import psycopg2
except ImportError:  # keep import-safe; DB paths raise a clear error when actually used
    psycopg2 = None

DB = "murderbot"
HERE = Path(__file__).resolve().parent
DISTILLED_PATH = HERE / "game_brain" / "knowledge_distilled.md"
PVP_BRAIN_PATH = HERE / "game_brain" / "pvp_brain.md"  # referenced, NEVER written by us
CONFIDENCE_TAG = "external-video"

# --- Evony domain vocabulary. A fragment is a candidate insight when it pairs game
# jargon with a concrete number — that is what makes it a TACTIC and not chatter. ---
HIGH_VALUE = {
    "rally", "rallies", "ghost", "ghosting", "bubble", "bubbles", "debuff", "debuffs",
    "layer", "layering", "layers", "counter", "counters", "siege", "mounted", "ranged",
    "ground", "tier", "hospital", "refine", "refining", "wall", "general", "generals",
    "reinforce", "reinforcement", "reinforcements", "monarch", "svs", "keep", "scout",
}
JARGON = HIGH_VALUE | {
    "troop", "troops", "buff", "buffs", "round", "rounds", "archer", "archers",
    "cavalry", "infantry", "pikemen", "swordsmen", "spearmen", "warrior", "warriors",
    "march", "marches", "marching", "stamina", "attack", "attacker", "defense",
    "defensive", "defender", "offense", "garrison", "boss", "bosses", "preset",
    "presets", "watchtower", "academy", "sanctum", "beast", "monster", "dragon",
    "gear", "medal", "medals", "kill", "kills", "points", "power", "subcity",
    "decoy", "frontline", "toe", "range", "hp", "atk", "def", "city", "castle",
    "duty", "buffs", "art", "spiritual", "warhall", "healing", "wounded",
}
JARGON_RE = re.compile(r"\b(" + "|".join(sorted(JARGON, key=len, reverse=True)) + r")\b", re.I)
TIER_RE = re.compile(r"\bt\s?\d{1,2}\b", re.I)
NUM_RE = re.compile(r"\b\d+(?:[.,]\d+)*\s?(?:%|x|k|m|b|k?ph)?\b", re.I)
SENT_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
STOP = {
    "the", "a", "an", "and", "or", "but", "if", "then", "so", "of", "to", "in", "on",
    "for", "with", "is", "are", "be", "you", "your", "i", "it", "that", "this", "at",
    "as", "we", "they", "he", "she", "them", "our", "my", "me", "do", "does", "can",
    "will", "would", "have", "has", "had", "get", "got", "going", "gonna", "just",
    "like", "really", "want", "when", "what", "how", "here", "there", "not", "no",
    "up", "out", "one", "two", "about", "into", "from", "by", "an", "all", "some",
    "more", "very", "kind", "sort", "okay", "yeah", "right", "know", "because", "put",
}


def _conn():
    if psycopg2 is None:
        raise RuntimeError(
            "psycopg2 is required for DB access. Run with the project venv, e.g. "
            "`.venv/bin/python knowledge_synth.py --synth`.")
    return psycopg2.connect(dbname=DB)


def _fetch_rows():
    """Return every knowledge row as a dict (source, source_id, title, url, topic, text)."""
    conn = _conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT source, source_id, COALESCE(title,''), COALESCE(url,''), "
        "COALESCE(topic,''), COALESCE(text,'') FROM knowledge "
        "WHERE text IS NOT NULL AND length(text) > 0 ORDER BY n_chars DESC")
    rows = [
        {"source": s, "source_id": sid, "title": t, "url": u, "topic": tp, "text": txt}
        for s, sid, t, u, tp, txt in cur.fetchall()
    ]
    cur.close()
    conn.close()
    return rows


# --------------------------------------------------------------------------- #
# Fragment extraction                                                         #
# --------------------------------------------------------------------------- #
def _clean(text):
    return re.sub(r"\s+", " ", (text or "").replace("​", " ")).strip()


def _segments(text):
    """Split a transcript/message into candidate fragments.

    Community captions are frequently un-punctuated, so we fall back to overlapping
    word windows when sentence punctuation is too sparse to split on."""
    text = _clean(text)
    if not text:
        return []
    words = text.split(" ")
    enders = text.count(".") + text.count("?") + text.count("!")
    if enders >= max(3, len(words) / 30):  # decently punctuated → real sentences
        segs = [s.strip() for s in SENT_SPLIT_RE.split(text) if s.strip()]
        return [s for s in segs if 6 <= len(s.split()) <= 55]
    # sparse punctuation → overlapping 24-word windows (step 12)
    size, step, out = 24, 12, []
    for i in range(0, max(1, len(words)), step):
        chunk = words[i:i + size]
        if len(chunk) >= 8:
            out.append(" ".join(chunk))
        if i + size >= len(words):
            break
    return out


def _signals(seg):
    """(list of number/tier tokens, set of jargon words) found in a fragment."""
    nums = TIER_RE.findall(seg) + [n for n in NUM_RE.findall(seg) if any(c.isdigit() for c in n)]
    jarg = {m.lower() for m in JARGON_RE.findall(seg)}
    return nums, jarg


def _focus(seg, nums, jarg):
    """Trim a window down to the span that actually carries the signal, for readability."""
    words = seg.split(" ")
    lowers = [w.lower().strip(".,!?;:()[]") for w in words]
    sig = set()
    for i, w in enumerate(words):
        lw = lowers[i]
        if lw in jarg or TIER_RE.match(w) or (any(c.isdigit() for c in w)):
            sig.add(i)
    if not sig:
        return seg
    lo, hi = max(0, min(sig) - 2), min(len(words), max(sig) + 3)
    if hi - lo < 6:  # too tight → keep original
        return seg
    frag = " ".join(words[lo:hi]).strip()
    prefix = "" if lo == 0 else "…"
    suffix = "" if hi >= len(words) else "…"
    return f"{prefix}{frag}{suffix}"


def _norm_key(text):
    """Normalized fingerprint for dedup / already-present detection."""
    toks = [t for t in re.findall(r"[a-z0-9%]+", text.lower()) if t not in STOP]
    return " ".join(toks)


def _tokset(text):
    return {t for t in re.findall(r"[a-z0-9%]+", text.lower()) if t not in STOP and len(t) > 1}


def _jaccard(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _score(nums, jarg):
    hv = len(jarg & HIGH_VALUE)
    return 3.0 * hv + 2.0 * len(nums) + len(jarg)


import re as _re2

_NOISE_RE = _re2.compile(
    r"\b(reply|subscribe|like and|link in|thanks for watching|check out my|"
    r"\d+\s+(years?|months?|weeks?|days?)\s+ago|hit the bell|smash that|"
    r"my channel|discord link|patreon|comment below|let me know)\b", _re2.I)


def _is_noise(seg):
    """Reject YouTube-comment / channel-boilerplate fragments that aren't real tactics."""
    if _NOISE_RE.search(seg):
        return True
    # a fragment that's mostly a username/handle or has no lowercase words is junk
    letters = [c for c in seg if c.isalpha()]
    if letters and sum(c.isupper() for c in letters) / len(letters) > 0.4:
        return True
    return False


def _candidate_insights(rows, per_video=8, min_score=6.0):
    """Extract, score, and dedupe candidate insight fragments across all knowledge rows.

    Returns a flat list of dicts: {text, title, url, source, source_id, topic,
    signals, score}. Deduped within a video and globally (token-set Jaccard)."""
    global_seen = []  # (tokset, score, index) for cross-video dedup
    out = []
    for row in rows:
        local = []
        for seg in _segments(row["text"]):
            if _is_noise(seg):
                continue
            nums, jarg = _signals(seg)
            concrete = len(nums) >= 1 and len(jarg) >= 1
            ruley = len(jarg & HIGH_VALUE) >= 2
            if not (concrete or ruley):
                continue
            score = _score(nums, jarg)
            if score < min_score:
                continue
            frag = _focus(seg, nums, jarg)
            wc = len(frag.split())
            if wc < 6 or wc > 55:
                continue
            local.append({"text": frag, "score": score, "nums": nums, "jarg": jarg,
                          "tokset": _tokset(frag)})
        # within-video dedup: keep the higher-scoring of near-duplicate windows
        local.sort(key=lambda c: c["score"], reverse=True)
        kept = []
        for c in local:
            if any(_jaccard(c["tokset"], k["tokset"]) > 0.55 for k in kept):
                continue
            kept.append(c)
            if len(kept) >= per_video:
                break
        # cross-video dedup
        for c in kept:
            if any(_jaccard(c["tokset"], gt) > 0.6 for gt in global_seen):
                continue
            global_seen.append(c["tokset"])
            signals = sorted(set(c["nums"]) | (c["jarg"] & HIGH_VALUE))
            out.append({
                "text": c["text"], "title": row["title"] or row["source_id"],
                "url": row["url"], "source": row["source"], "source_id": row["source_id"],
                "topic": row["topic"], "signals": signals, "score": round(c["score"], 1),
            })
    out.sort(key=lambda d: d["score"], reverse=True)
    return out


# --------------------------------------------------------------------------- #
# Optional Moonshot / Kimi refinement (never blocks, never required)          #
# --------------------------------------------------------------------------- #
def _llm_refine(title, fragments, timeout=None, model=None):
    """Ask Kimi to rewrite raw fragments into clean one-line Evony rules.
    Returns a list of strings, or None on any failure (caller keeps the heuristic)."""
    key = os.environ.get("MOONSHOT_API_KEY")
    if not key or not fragments:
        return None
    import urllib.error
    import urllib.request
    timeout = float(timeout if timeout is not None else os.environ.get("KNOWLEDGE_SYNTH_LLM_TIMEOUT", 20))
    base = os.environ.get("MOONSHOT_BASE_URL", "https://api.moonshot.cn/v1").rstrip("/")
    models = [m for m in (model, os.environ.get("MOONSHOT_MODEL"),
                          "kimi-k2-0711-preview", "moonshot-v1-8k") if m]
    system = ("You distill Evony: The King's Return strategy transcripts into concrete, "
              "reusable RULES. Output ONLY a JSON array of short strings. Each string is one "
              "actionable tactic that keeps its concrete numbers (tiers like T14, percentages, "
              "multipliers, counts). Drop filler, greetings, and anything without game content. "
              "Do not invent numbers not present in the input. Max 10 rules.")
    user = (f"VIDEO: {title}\n\nRAW FRAGMENTS:\n- " + "\n- ".join(fragments[:24]) +
            "\n\nReturn a JSON array of distilled rule strings.")
    for m in models:
        payload = json.dumps({"model": m, "temperature": 0.2, "max_tokens": 700,
                              "messages": [{"role": "system", "content": system},
                                           {"role": "user", "content": user}]}).encode()
        req = urllib.request.Request(f"{base}/chat/completions", data=payload,
                                     headers={"Authorization": f"Bearer {key}",
                                              "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = json.loads(resp.read().decode())
            text = (body.get("choices") or [{}])[0].get("message", {}).get("content", "").strip()
            if not text:
                continue
            text = re.sub(r"^```(?:json)?|```$", "", text.strip()).strip()
            arr = json.loads(text)
            rules = [str(x).strip() for x in arr if str(x).strip()]
            if rules:
                return rules
        except urllib.error.HTTPError as exc:
            if exc.code in (400, 404) and m != models[-1]:
                continue
            return None
        except (urllib.error.URLError, OSError, ValueError, TimeoutError, json.JSONDecodeError):
            return None
    return None


# --------------------------------------------------------------------------- #
# Distilled-file read / write                                                 #
# --------------------------------------------------------------------------- #
_HEADER = (
    "# Murder Bot — Distilled External Learning\n\n"
    "Auto-generated by `knowledge_synth.py` from the Postgres `knowledge` table (external\n"
    "YouTube/Discord Evony content ingested by `knowledge_ingest.py` / `discord_ingest.py`).\n"
    "These are heuristic/LLM extractions from **community** videos — directional, NOT the\n"
    "hand-verified doctrine. The authoritative combat model lives in `pvp_brain.md`; this file\n"
    f"is APPEND-ONLY and never overwrites it. Every insight is tagged `confidence: {CONFIDENCE_TAG}`\n"
    "and attributed to its source. `relevant(query, k)` searches these so advisors can cite them.\n\n"
    "<!-- knowledge_synth:managed -->\n"
)


def _existing_keys(path):
    """Normalized fingerprints of insights already written (for idempotent appends)."""
    if not path.exists():
        return set()
    keys = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"\s*[-*]\s+(.*)", line)
        if m:
            body = re.sub(r"`[^`]*`\s*$", "", m.group(1)).strip()  # strip trailing signal tag
            keys.add(_norm_key(body))
    return keys


def synth(use_llm=None, per_video=8, path=None, min_score=6.0):
    """Distill the knowledge base into game_brain/knowledge_distilled.md (append-only).

    Returns a summary dict: {sources, candidates, new, skipped_existing, total_after,
    llm_used, path}. Prints nothing (CLI handles output)."""
    path = Path(path) if path else DISTILLED_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = _fetch_rows()
    cands = _candidate_insights(rows, per_video=per_video, min_score=min_score)

    want_llm = use_llm if use_llm is not None else bool(os.environ.get("MOONSHOT_API_KEY"))
    llm_used = False
    if want_llm:
        # group heuristic fragments by video, ask Kimi to refine; on success, replace
        by_vid = {}
        for c in cands:
            by_vid.setdefault((c["title"], c["url"], c["source"], c["source_id"], c["topic"]), []).append(c)
        refined = []
        for (title, url, source, sid, topic), items in by_vid.items():
            rules = _llm_refine(title, [c["text"] for c in items])
            if rules:
                llm_used = True
                for r in rules:
                    nums, jarg = _signals(r)
                    refined.append({"text": r, "title": title, "url": url, "source": source,
                                    "source_id": sid, "topic": topic,
                                    "signals": sorted(set(nums) | (jarg & HIGH_VALUE)),
                                    "score": round(_score(nums, jarg), 1)})
            else:
                refined.extend(items)  # fall back to this video's heuristic fragments
        if llm_used:
            cands = refined

    existing = _existing_keys(path)
    new, seen_now = [], set()
    for c in cands:
        key = _norm_key(c["text"])
        if not key or key in existing or key in seen_now:
            continue
        seen_now.add(key)
        new.append(c)

    if not path.exists():
        path.write_text(_HEADER, encoding="utf-8")

    total_after = len(existing) + len(new)
    if new:
        stamp = _dt.datetime.now().strftime("%Y-%m-%d %H:%M")
        method = "Moonshot/Kimi + heuristic" if llm_used else "heuristic"
        lines = [f"\n## Synth run {stamp} — {len(new)} new insights ({method})\n"]
        # group new insights back by source video for attribution
        groups = {}
        for c in new:
            groups.setdefault((c["title"], c["url"], c["source"], c["source_id"]), []).append(c)
        for (title, url, source, sid), items in groups.items():
            src_line = f"_source: {source}"
            if url:
                src_line += f" · {url}"
            src_line += f" · confidence: {CONFIDENCE_TAG}_"
            lines.append(f"### {title}\n{src_line}\n")
            for c in sorted(items, key=lambda d: d["score"], reverse=True):
                tag = f"  `[{', '.join(c['signals'][:6])}]`" if c["signals"] else ""
                lines.append(f"- {c['text']}{tag}")
            lines.append("")
        with path.open("a", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")

    return {"sources": len(rows), "candidates": len(cands), "new": len(new),
            "skipped_existing": len(cands) - len(new), "total_after": total_after,
            "llm_used": llm_used, "path": str(path)}


# --------------------------------------------------------------------------- #
# relevant() — the citation API advisors call                                 #
# --------------------------------------------------------------------------- #
def relevant(query, k=5, rows=None, per_video=12):
    """Return the top-k external-learning snippets for a situation, TF/keyword ranked.

    Each result: {text, title, url, source, confidence, score, signals}. Built live from
    the knowledge base so it works even before synth() has been run. counter_ai and
    general_advisor call this to CITE what the community teaches for the current lead."""
    rows = rows if rows is not None else _fetch_rows()
    cands = _candidate_insights(rows, per_video=per_video, min_score=4.0)
    q_terms = [t for t in re.findall(r"[a-z0-9%]+", (query or "").lower())
               if t not in STOP and len(t) > 1]
    if not q_terms:
        return []
    q_set = set(q_terms)
    scored = []
    for c in cands:
        low = c["text"].lower()
        tf = sum(low.count(t) for t in q_terms)
        if tf <= 0:
            continue
        overlap = len(q_set & c.get("tokset", _tokset(c["text"])))
        rank = tf + 1.5 * overlap + 0.1 * c["score"]
        scored.append((rank, c))
    scored.sort(key=lambda x: x[0], reverse=True)
    results = []
    seen = []
    for rank, c in scored:
        ts = _tokset(c["text"])
        if any(_jaccard(ts, s) > 0.6 for s in seen):
            continue
        seen.append(ts)
        results.append({"text": c["text"], "title": c["title"], "url": c["url"],
                        "source": c["source"], "confidence": CONFIDENCE_TAG,
                        "score": round(float(rank), 2), "signals": c["signals"]})
        if len(results) >= k:
            break
    return results


# --------------------------------------------------------------------------- #
# Stats                                                                        #
# --------------------------------------------------------------------------- #
def stats():
    rows = _fetch_rows()
    by_source = {}
    for r in rows:
        b = by_source.setdefault(r["source"], {"docs": 0, "chars": 0})
        b["docs"] += 1
        b["chars"] += len(r["text"])
    cands = _candidate_insights(rows)
    distilled = 0
    if DISTILLED_PATH.exists():
        distilled = len(_existing_keys(DISTILLED_PATH))
    return {"raw_docs": len(rows), "by_source": by_source,
            "candidate_insights": len(cands), "distilled_in_file": distilled,
            "distilled_path": str(DISTILLED_PATH),
            "distilled_exists": DISTILLED_PATH.exists()}


# --------------------------------------------------------------------------- #
# CLI                                                                          #
# --------------------------------------------------------------------------- #
def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Distill external Evony learning from the knowledge table into "
                    "game_brain/knowledge_distilled.md (append-only) and serve relevant() snippets.")
    ap.add_argument("--synth", action="store_true", help="distill the knowledge base (append + diff summary)")
    ap.add_argument("--stats", action="store_true", help="show raw + distilled coverage")
    ap.add_argument("--query", metavar="Q", help="test relevant(): print top-k snippets for a situation")
    ap.add_argument("-k", type=int, default=5, help="how many snippets for --query")
    ap.add_argument("--per-video", type=int, default=8, help="max insights kept per source video")
    ap.add_argument("--llm", action="store_true", help="force the Moonshot/Kimi refinement pass")
    ap.add_argument("--no-llm", action="store_true", help="force heuristic-only (offline)")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    a = ap.parse_args(argv)

    use_llm = True if a.llm else (False if a.no_llm else None)

    if a.query:
        res = relevant(a.query, a.k)
        if a.json:
            print(json.dumps(res, indent=2))
        else:
            print(f"relevant({a.query!r}, k={a.k}) — top external-learning snippets:\n")
            for i, r in enumerate(res, 1):
                print(f"{i}. [{r['score']}] {r['text']}")
                print(f"     ↳ {r['title']} ({r['url'] or r['source']}) · confidence: {r['confidence']}"
                      + (f" · signals {r['signals'][:6]}" if r["signals"] else ""))
            if not res:
                print("  (no matching snippets)")
        return 0

    if a.synth:
        summary = synth(use_llm=use_llm, per_video=a.per_video)
        if a.json:
            print(json.dumps(summary, indent=2))
        else:
            print(f"synth: {summary['sources']} sources → {summary['candidates']} candidate insights; "
                  f"{summary['new']} NEW appended, {summary['skipped_existing']} already present.")
            print(f"       distilled file now holds {summary['total_after']} insights "
                  f"(LLM {'used' if summary['llm_used'] else 'not used — heuristic'}).")
            print(f"       → {summary['path']}")
        if not (a.stats):
            return 0

    if a.stats or not (a.synth or a.query):
        s = stats()
        if a.json:
            print(json.dumps(s, indent=2))
        else:
            print(f"knowledge_synth stats:")
            print(f"  raw docs: {s['raw_docs']}")
            for src, b in s["by_source"].items():
                print(f"    {src}: {b['docs']} docs, {b['chars']:,} chars")
            print(f"  candidate insights extractable: {s['candidate_insights']}")
            print(f"  distilled insights in file: {s['distilled_in_file']} "
                  f"({'exists' if s['distilled_exists'] else 'not created yet'})")
            print(f"  → {s['distilled_path']}")
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
