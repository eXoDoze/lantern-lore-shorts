"""Free stock footage: Pixabay (main), Pexels (optional), generated fog as last resort.

Whatever happens, this module always returns a usable clip, so a missing or broken
footage service never stops the daily upload.
"""

import json
import os
import random
import re
import subprocess
from pathlib import Path

import requests

from . import channel_config as cfg
from .llm_gemini_client import generate_json

PIXABAY_URL = "https://pixabay.com/api/videos/"
PEXELS_URLS = ["https://api.pexels.com/v1/videos/search", "https://api.pexels.com/videos/search"]


# ------------------------------------------------------------------ Pixabay
def _pixabay_candidates(query, landscape=False):
    key = os.environ.get("PIXABAY_API_KEY", "").strip()
    if not key:
        return []
    try:
        r = requests.get(PIXABAY_URL, params={"key": key, "q": query[:100], "per_page": 30,
                                              "safesearch": "true", "video_type": "film"}, timeout=30)
        r.raise_for_status()
        hits = r.json().get("hits", [])
    except (requests.RequestException, ValueError) as exc:
        print(f"[footage] Pixabay error: {exc}")
        return []
    out = []
    for h in hits:
        files = [v for v in (h.get("videos") or {}).values() if isinstance(v, dict) and v.get("url")]
        if not files:
            continue
        portrait = [f for f in files if f.get("height", 0) >= f.get("width", 1)]
        wide = [f for f in files if f.get("width", 0) > f.get("height", 0)]
        pool = (wide or files) if landscape else (portrait or files)
        best = min(pool, key=lambda f: abs(max(f.get("height", 0), f.get("width", 0)) - 1920))
        out.append({
            "uid": f"pixabay:{h['id']}",
            "tags": str(h.get("tags", "")).lower(),
            "link": best["url"],
            "duration": h.get("duration", 0),
            "portrait": bool(portrait),
            "author": h.get("user", "Pixabay"),
            "source": "Pixabay",
        })
    return out


# ------------------------------------------------------------------ Pexels (only if a key exists)
def _pexels_candidates(query, landscape=False):
    key = os.environ.get("PEXELS_API_KEY", "").strip()
    if not key:
        return []
    for url in PEXELS_URLS:
        try:
            r = requests.get(url, headers={"Authorization": key},
                             params={"query": query, "per_page": 20, "orientation": "landscape" if landscape else "portrait"}, timeout=30)
            if r.status_code == 404:
                continue
            r.raise_for_status()
            out = []
            for v in r.json().get("videos", []):
                files = [f for f in v.get("video_files", []) if f.get("link") and f.get("width") and f.get("height")]
                if not files:
                    continue
                best = min(files, key=lambda f: abs(max(f["height"], f["width"]) - 1920))
                out.append({
                    "uid": f"pexels:{v['id']}",
                    # Pexels has no tags, but the page URL contains a description ("/video/foggy-forest-at-night-123/")
                    "tags": " ".join(re.findall(r"[a-z]+", (v.get("url") or "").lower().split("/video/")[-1])),
                    "link": best["link"],
                    "duration": v.get("duration", 0),
                    "portrait": best["height"] >= best["width"],
                    "author": (v.get("user") or {}).get("name", "Pexels"),
                    "source": "Pexels",
                })
            return out
        except (requests.RequestException, ValueError) as exc:
            print(f"[footage] Pexels error: {exc}")
    return []


# ------------------------------------------------------------------ generated fallback
def _generated_fog(seconds, path, landscape=False):
    """Dark drifting fog made from noise - original, needs no service at all."""
    u, v = random.choice([(124, 130), (132, 124), (126, 126), (130, 132)])  # slight colour tint
    vf = (
        "format=yuv420p,noise=c0s=100:c0f=t,tmix=frames=20,gblur=sigma=1.2,"
        f"scale={'1920:1080' if landscape else '1080:1920'}:flags=bicubic,eq=contrast=2.2:brightness=-0.12,lutyuv=u={u}:v={v},format=yuv420p"
    )
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "lavfi", "-i", f"color=c=0x606060:s={'48x27' if landscape else '27x48'}:r=30:d={seconds + 1:.2f}",
        "-vf", vf, "-c:v", "libx264", "-preset", "veryfast", "-crf", "24", str(path)], check=True)


def _download(link, path):
    with requests.get(link, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(path, "wb") as fh:
            for chunk in r.iter_content(1 << 20):
                fh.write(chunk)


def fetch_clip(query, min_seconds, work_dir, used_ids, index, landscape=False):
    path = Path(work_dir) / f"clip_{index}.mp4"
    queries = [query] + random.sample(cfg.FALLBACK_FOOTAGE_QUERIES, 3)
    for q in queries:
        candidates = [c for c in _pixabay_candidates(q, landscape) + _pexels_candidates(q, landscape) if c["uid"] not in used_ids]
        if not candidates:
            continue
        # prefer clips that are long enough, then the right orientation
        candidates.sort(key=lambda c: (c["duration"] < min_seconds, c["portrait"] == landscape, random.random()))
        for c in candidates[:5]:
            try:
                _download(c["link"], path)
            except requests.RequestException as exc:
                print(f"[footage] download failed: {exc}")
                continue
            used_ids.add(c["uid"])
            return {"path": str(path), "id": c["uid"], "author": c["author"], "source": c["source"]}
    print(f"[footage] No stock clip for '{query}' -> generated fog background")
    _generated_fog(min_seconds, path, landscape)
    return {"path": str(path), "id": f"fog:{index}", "author": "original", "source": "generated"}


# ------------------------------------------------------------------ smart selection
# Words that fit the channel's dark mood, and words that clearly do not.
MOOD_GOOD = {"night", "dark", "darkness", "fog", "foggy", "mist", "misty", "moon", "moonlight", "storm", "rain",
             "shadow", "shadows", "smoke", "candle", "abandoned", "old", "ancient", "winter", "snow", "forest",
             "woods", "cave", "ruins", "lantern", "silhouette", "clouds", "dusk", "twilight", "gloomy", "haunted",
             "mystery", "eerie", "creepy", "spooky", "cemetery", "grave", "church", "cabin", "barn", "lighthouse",
             "waves", "sea", "ocean", "mountain", "mountains", "road", "night sky", "stars", "fire", "flame"}
MOOD_BAD = {"sunny", "summer", "beach", "umbrella", "parasol", "flower", "flowers", "blossom", "blooming", "colorful",
            "happy", "smile", "smiling", "party", "holiday", "tropical", "vacation", "sunshine", "picnic", "wedding",
            "fashion", "food", "business", "office", "shopping", "sport", "fitness", "yoga", "christmas", "toy"}
PEOPLE = {"woman", "man", "girl", "boy", "people", "child", "children", "person", "couple", "family",
          "portrait", "model", "face", "selfie", "lady", "kid"}
ANIMALS = {"bird", "birds", "kingfisher", "cat", "dog", "horse", "cow", "insect", "butterfly", "bee", "fish",
           "duck", "squirrel", "deer", "sheep", "goat", "chicken", "parrot", "owl", "wolf", "bat", "crow", "raven"}


def _words(text):
    return set(re.findall(r"[a-z]+", text.lower()))


def _score(candidate, query, narration):
    tags = _words(candidate["tags"])
    wanted = _words(query) - {"a", "the", "of", "in", "at", "on", "and", "with"}
    story = _words(narration)
    overlap = len(tags & wanted)
    if overlap == 0:
        return None  # nothing in common with what the scene asked for
    score = 3 * overlap + len(tags & MOOD_GOOD)
    score -= 4 * len(tags & MOOD_BAD - story)
    score -= 3 * len(tags & PEOPLE - story)
    score -= 3 * len(tags & ANIMALS - story - wanted)   # a kingfisher in a ghost-ship story -> out
    return score


def _scene_candidates(scene, narration, used_ids, landscape):
    queries = [q for q in (scene.get("footage_queries") or []) if isinstance(q, str) and q.strip()]
    queries = (queries or [scene.get("footage_query", "")])[:3]
    seen, scored = set(), []
    for q in queries:
        for c in _pixabay_candidates(q, landscape) + _pexels_candidates(q, landscape):
            if c["uid"] in used_ids or c["uid"] in seen:
                continue
            seen.add(c["uid"])
            sc = _score(c, q, narration)
            if sc is not None and sc > 0:
                c["score"] = sc
                scored.append(c)
    scored.sort(key=lambda c: (c["score"], c["portrait"] != landscape), reverse=True)
    return scored[:6]


def _llm_pick(scenes, candidates_per_scene):
    """One Gemini call that picks the best fitting clip for every scene based on the clip descriptions."""
    blocks = []
    for i, (scene, cands) in enumerate(zip(scenes, candidates_per_scene)):
        options = "\n".join(f"    {j}: {c['tags']} ({c['duration']}s)" for j, c in enumerate(cands)) or "    (none)"
        blocks.append(f"Scene {i}: \"{scene['narration'][:300]}\"\n  Clips:\n{options}")
    prompt = ("You are the video editor of a dark, atmospheric storytelling channel (legends, ghost stories).\n"
              "For every scene pick the stock clip whose description fits the narration and the eerie mood best. "
              "A clip must not contradict the scene (wrong place, season, cheerful or touristy look, random animals "
              "or people). If no clip fits at all, answer -1 for that scene.\n\n"
              + "\n\n".join(blocks)
              + '\n\nReturn JSON: {"choices": [index for scene 0, index for scene 1, ...]}')
    try:
        data = generate_json(prompt, temperature=0.1)
        choices = data.get("choices") if isinstance(data, dict) else None
        if isinstance(choices, list) and len(choices) == len(scenes):
            return [int(c) if isinstance(c, (int, float)) or str(c).lstrip("-").isdigit() else 0 for c in choices]
    except Exception as exc:  # noqa: BLE001
        print(f"[footage] Clip selection by Gemini skipped ({exc})")
    return [0] * len(scenes)


def choose_clips(scenes, scene_lengths, work_dir, used_ids, landscape=False):
    """Finds, judges and downloads one clip per scene. Always returns a clip for every scene."""
    candidates = [_scene_candidates(s, s["narration"], used_ids, landscape) for s in scenes]
    picks = _llm_pick(scenes, candidates)
    clips = []
    for i, (scene, cands, pick, length) in enumerate(zip(scenes, candidates, picks, scene_lengths)):
        path = Path(work_dir) / f"clip_{i}.mp4"
        order = []
        if 0 <= pick < len(cands):
            order.append(cands[pick])
        order += [c for j, c in enumerate(cands) if j != pick and pick != -1]
        chosen = None
        for c in order:
            if c["uid"] in used_ids:
                continue
            try:
                _download(c["link"], path)
            except requests.RequestException as exc:
                print(f"[footage] download failed: {exc}")
                continue
            chosen = c
            break
        if chosen:
            used_ids.add(chosen["uid"])
            print(f"[footage] Scene {i}: {chosen['source']} clip '{chosen['tags'][:60]}'")
            clips.append({"path": str(path), "id": chosen["uid"], "author": chosen["author"], "source": chosen["source"]})
        else:
            # nothing fitting -> atmospheric generic clip, then generated fog as last resort
            print(f"[footage] Scene {i}: no fitting clip, using a generic mood shot")
            clips.append(fetch_clip(random.choice(cfg.FALLBACK_FOOTAGE_QUERIES), length, work_dir, used_ids, i, landscape))
    return clips
