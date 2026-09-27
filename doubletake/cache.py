"""Content-addressed cache of examinations, so the stage replays instantly and offline.

The key covers everything that changes Jev's answers: sender, text, Jev model, the question set and the
household context. Decisions (τ, flags) are stored as computed at the time.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from . import config
from .data import Message, registry
from .engine import Engine, questions

CACHE_DIR = config.DATA / "cache"


def key(msg: Message) -> str:
    blob = json.dumps({"sender": msg.sender, "text": msg.text, "model": config.JEV_MODEL,
                       "llm": config.SECOND_OPINION_MODEL, "questions": questions(),
                       "household": registry().context()}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def path_for(msg: Message, root: Path = CACHE_DIR) -> Path:
    return root / f"{msg.id}-{key(msg)}.json"


def get(msg: Message, root: Path = CACHE_DIR) -> dict | None:
    p = path_for(msg, root)
    return json.loads(p.read_text()) if p.exists() else None


def put(msg: Message, examination: dict, root: Path = CACHE_DIR) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for old in root.glob(f"{msg.id}-*.json"):  # keep one entry per message id
        old.unlink()
    p = path_for(msg, root)
    p.write_text(json.dumps(examination, indent=1, ensure_ascii=False))
    return p


async def examine_cached(engine: Engine, msg: Message, refresh: bool = False, root: Path = CACHE_DIR) -> tuple[dict, bool]:
    """Returns (examination dict, from_cache)."""
    if not refresh and (hit := get(msg, root)):
        return hit, True
    ex = (await engine.examine(msg)).to_dict()
    put(msg, ex, root)
    return ex, False
