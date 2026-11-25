"""Chooses the next series and a fresh, never-used topic - fully automatic."""

import difflib
import json
import random
import re
from datetime import datetime, timezone
from pathlib import Path

from . import channel_config as cfg
from .llm_gemini_client import generate_json

HISTORY_FILE = Path(__file__).resolve().parent.parent / "data" / "published_history.json"


def load_history():
    if HISTORY_FILE.exists():
        return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    return {"videos": []}


def save_history(history):
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_FILE.write_text(json.dumps(history, indent=2, ensure_ascii=False), encoding="utf-8")


def uploads_today(history):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return sum(1 for v in history["videos"] if v.get("date", "").startswith(today) and v.get("video_id"))


def _normalize(text):
    return re.sub(r"[^a-z0-9 ]", "", text.lower()).strip()


def is_duplicate(subject, used_subjects):
    norm = _normalize(subject)
    if not norm:
        return True
    for used in used_subjects:
        u = _normalize(used)
        if norm == u or difflib.SequenceMatcher(None, norm, u).ratio() > 0.82:
            return True
    return False


def pick_series(history, forced_key=None, multipliers=None):
    if forced_key:
        for s in cfg.SERIES:
            if s["key"] == forced_key:
                return s
        print(f"[topics] Unknown series '{forced_key}', choosing automatically.")
    window = history["videos"][-len(cfg.SERIES) * 3:]
    last_key = history["videos"][-1]["series"] if history["videos"] else None

    def score(series):
        recent = sum(1 for v in window if v.get("series") == series["key"])
        factor = (multipliers or {}).get(series["key"], 1.0)
        return recent / (series["weight"] * factor) + random.random() * 0.3

    candidates = [s for s in cfg.SERIES if s["key"] != last_key] or cfg.SERIES
    return min(candidates, key=score)


def find_new_topic(series, history):
    used = [v.get("subject", "") for v in history["videos"]]
    used_in_series = [v.get("subject", "") for v in history["videos"] if v.get("series") == series["key"]]
    avoid_list = "\n".join(f"- {s}" for s in used_in_series[-400:]) or "- (nothing yet)"

    if series["fiction"]:
        task = (
            "Invent 6 different premises for ORIGINAL short horror stories. Each premise must be new, "
            "not based on an existing story, film, creepypasta or book."
        )
    else:
        task = (
            "List 8 different REAL legends, folklore subjects, places or historical mysteries that fit the "
            "series. They must genuinely exist in folklore or historical record (do not invent legends). "
            "Prefer lesser-known but intriguing subjects over the most famous ones about half of the time."
        )

    prompt = f"""You plan topics for the YouTube Shorts channel "{cfg.CHANNEL_NAME}".
Series: {series['label']}
Series description: {series['brief']}

{task}

Do NOT repeat or closely resemble any of these already published subjects:
{avoid_list}

Rules: nothing involving living private individuals, no crimes after 1975, no real victims of recent tragedies,
no sacred or closed Indigenous traditions (for example skinwalkers), nothing sexual, no gore.

Return JSON: {{"topics": [{{"subject": "short unique name of the subject (max 8 words)",
"angle": "one sentence: the eerie angle or hook the short will focus on",
"region": "place or region"}}]}}"""

    for _ in range(3):
        data = generate_json(prompt, temperature=1.0)
        topics = data.get("topics", []) if isinstance(data, dict) else data
        random.shuffle(topics)
        for t in topics:
            subject = str(t.get("subject", "")).strip()
            if subject and not is_duplicate(subject, used):
                return {"subject": subject, "angle": t.get("angle", ""), "region": t.get("region", "")}
    return None
