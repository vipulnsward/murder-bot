"""Serializable Evony skill catalog with local retrieval and live verification."""

from __future__ import annotations

import hashlib
import importlib
import inspect
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

import shared_capture


DEVICE = "127.0.0.1:5555"
ROOT = Path(__file__).resolve().parent
INDEX_PATH = ROOT / "game_brain" / "skill_index.json"
VECTOR_PATH = ROOT / "game_brain" / "skill_index.npy"
HASH_DIMENSIONS = 512


@dataclass
class Skill:
    name: str
    description: str
    fn: str
    tags: list[str] = field(default_factory=list)
    verify: str = ""


DEFAULT_SKILLS = (
    Skill(
        "join_monster_rallies",
        "Navigate to Alliance War Monster War and join forming boss-monster rallies "
        "with the saved preset, then return to city.",
        "live_rally:run",
        ["rally", "monster", "alliance", "action"],
        "is_city",
    ),
    Skill(
        "open_monster_war",
        "Open the Alliance War Monster War screen to view forming boss-monster rallies.",
        "live_rally:open_monster_war",
        ["rally", "monster", "navigation", "action"],
        "on_war_screen",
    ),
    Skill(
        "dismiss_popups",
        "Dismiss blocking purchase popups, reward banners, dialogs, and menus to reveal the city.",
        "live_map:clear_popups",
        ["popup", "city", "navigation", "action"],
        "no_popup",
    ),
    Skill(
        "exit_ideal_land",
        "Leave the decorative Ideal Land area and return to the main city.",
        "live_map:exit_ideal_land",
        ["ideal-land", "city", "navigation", "action"],
        "not_ideal_land",
    ),
    Skill(
        "read_city_stats",
        "Read city HUD resources, power, gems, and VIP stats without changing the game state.",
        "game_hud:read_hud",
        ["hud", "resources", "power", "gems", "read-only"],
        "hud_ok",
    ),
    Skill(
        "detect_buildings",
        "Detect candidate city building locations in the current frame without tapping anything.",
        "live_map:find_building_candidates",
        ["buildings", "vision", "city", "read-only"],
        "buildings_detected",
    ),
    Skill(
        "classify_screen",
        "Classify the current game screen into a learned state label using local vision and OCR.",
        "gen_fsm:classify",
        ["screen", "vision", "state", "read-only"],
        "valid_screen_label",
    ),
)


class SkillLibrary:
    def __init__(self, index_path=INDEX_PATH):
        self.index_path = Path(index_path)
        self.vector_path = self.index_path.with_suffix(".npy")
        self.skills: dict[str, Skill] = {}
        self.vectors: np.ndarray | None = None
        self.embedding_backend: str | None = None
        self.similarity_scores: dict[str, float] = {}
        self._model = None
        if not self._load():
            for skill in DEFAULT_SKILLS:
                self.register(skill)

    def register(self, skill):
        if not isinstance(skill, Skill):
            raise TypeError("skill must be a Skill")
        self.skills[skill.name] = skill
        self.vectors = None

    @staticmethod
    def _tokens(text):
        words = re.findall(r"[a-z0-9]+", text.lower())
        return [word[:-3] + "y" if word.endswith("ies") else word[:-1]
                if len(word) > 3 and word.endswith("s") else word for word in words]

    @classmethod
    def _hash_embed(cls, texts):
        vectors = np.zeros((len(texts), HASH_DIMENSIONS), dtype=np.float32)
        for row, value in enumerate(texts):
            for token in cls._tokens(value):
                digest = hashlib.blake2b(token.encode(), digest_size=8).digest()
                vectors[row, int.from_bytes(digest, "little") % HASH_DIMENSIONS] += 1
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        return vectors / np.maximum(norms, 1)

    def _sentence_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer("all-MiniLM-L6-v2", local_files_only=True)
        return self._model

    def embed_all(self):
        descriptions = [skill.description for skill in self.skills.values()]
        try:
            model = self._sentence_model()
            self.vectors = np.asarray(
                model.encode(descriptions, normalize_embeddings=True), dtype=np.float32
            )
            self.embedding_backend = "sentence-transformers/all-MiniLM-L6-v2"
        except Exception:
            self._model = None
            self.vectors = self._hash_embed(descriptions)
            self.embedding_backend = "numpy hashing bag-of-words fallback"
        self._persist()
        print(f"Embedding backend: {self.embedding_backend}")
        return self.vectors

    def retrieve(self, query, k=5):
        if self.vectors is None:
            self.embed_all()
        if self.embedding_backend and self.embedding_backend.startswith("sentence-transformers"):
            try:
                query_vector = np.asarray(
                    self._sentence_model().encode([query], normalize_embeddings=True)[0],
                    dtype=np.float32,
                )
            except Exception:
                self.vectors = None
                self.embed_all()
                query_vector = self._hash_embed([query])[0]
        else:
            query_vector = self._hash_embed([query])[0]
        scores = self.vectors @ query_vector
        skills = list(self.skills.values())
        order = np.argsort(-scores, kind="stable")[:max(0, min(k, len(skills)))]
        self.similarity_scores = {skills[index].name: float(scores[index]) for index in order}
        return [skills[index] for index in order]

    def run(self, name_or_skill, **kwargs):
        try:
            skill = self.skills[name_or_skill] if isinstance(name_or_skill, str) else name_or_skill
            function = self._resolve(skill.fn)
            result = self._call(function, kwargs)
        except Exception as exc:
            return {"ok": False, "verified": False, "result": None,
                    "error": f"{type(exc).__name__}: {exc}"}

        frame = shared_capture.grab_wait(DEVICE)
        if frame is None:
            return {"ok": True, "verified": False, "result": result,
                    "error": "No fresh shared frame available for verification"}
        try:
            verified = bool(self._resolve_verify(skill.verify)(frame))
            return {"ok": True, "verified": verified, "result": result, "error": None}
        except Exception as exc:
            return {"ok": True, "verified": False, "result": result,
                    "error": f"{type(exc).__name__}: {exc}"}

    @staticmethod
    def _resolve(path):
        module_name, separator, function_name = path.partition(":")
        if not separator:
            raise ValueError(f"Callable path must be module:function: {path}")
        return getattr(importlib.import_module(module_name), function_name)

    @classmethod
    def _resolve_verify(cls, path):
        return cls._resolve(path) if ":" in path else getattr(importlib.import_module("verify"), path)

    @staticmethod
    def _call(function, kwargs):
        try:
            inspect.signature(function).bind(**kwargs)
        except TypeError:
            required = [
                parameter for parameter in inspect.signature(function).parameters.values()
                if parameter.default is inspect.Parameter.empty
                and parameter.kind in (parameter.POSITIONAL_ONLY, parameter.POSITIONAL_OR_KEYWORD)
                and parameter.name not in kwargs
            ]
            if len(required) != 1 or required[0].name not in {"frame", "img", "img_or_texts"}:
                raise
            frame = shared_capture.grab_wait(DEVICE)
            if frame is None:
                raise RuntimeError("No fresh shared frame available for read-only skill")
            return function(frame, **kwargs)
        return function(**kwargs)

    def _persist(self):
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        vector_tmp = self.vector_path.with_suffix(".npy.tmp")
        with vector_tmp.open("wb") as handle:
            np.save(handle, self.vectors)
        vector_tmp.replace(self.vector_path)
        payload = {
            "version": 1,
            "embedding_backend": self.embedding_backend,
            "vector_file": self.vector_path.name,
            "skills": [asdict(skill) for skill in self.skills.values()],
        }
        json_tmp = self.index_path.with_suffix(".json.tmp")
        json_tmp.write_text(json.dumps(payload, indent=2) + "\n")
        json_tmp.replace(self.index_path)

    def _load(self):
        try:
            payload = json.loads(self.index_path.read_text())
            vectors = np.load(self.vector_path, allow_pickle=False)
            skills = [Skill(**item) for item in payload["skills"]]
            if vectors.shape[0] != len(skills):
                return False
            self.skills = {skill.name: skill for skill in skills}
            self.vectors = np.asarray(vectors, dtype=np.float32)
            self.embedding_backend = payload["embedding_backend"]
            return True
        except (OSError, EOFError, ValueError, KeyError, TypeError):
            return False


def _result_summary(name, result):
    if name == "read_city_stats" and isinstance(result, dict):
        return (f"hud_ok={result.get('ok')} power={result.get('power')} "
                f"gems={result.get('gems')} vip={result.get('vip')} "
                f"resources={result.get('resources')}")
    if name == "classify_screen" and isinstance(result, tuple) and len(result) == 2:
        return f"label={result[0]} score={result[1]}"
    if name == "detect_buildings" and result is not None:
        return f"candidate_count={len(result)}"
    return repr(result)


if __name__ == "__main__":
    library = SkillLibrary()
    if library.vectors is None:
        library.embed_all()
    print(f"Registered skills: {len(library.skills)}")
    print(f"Embedding backend: {library.embedding_backend}")
    for query in ("join a monster rally", "get resources / power"):
        print(f"Retrieval: {query!r}")
        for skill in library.retrieve(query, k=3):
            print(f"  {skill.name}: {library.similarity_scores[skill.name]:.4f}")
    for name in ("read_city_stats", "classify_screen", "detect_buildings"):
        outcome = library.run(name)
        shown = {"ok": outcome["ok"], "verified": outcome["verified"],
                 "result-summary": _result_summary(name, outcome["result"])}
        print(f"{name}: {shown}")
        if outcome["error"]:
            print(f"  error: {outcome['error']}")
