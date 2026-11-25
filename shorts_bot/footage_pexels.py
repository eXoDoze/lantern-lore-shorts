"""Downloads free stock footage from Pexels (free API key, commercial use allowed)."""

import os
import random
from pathlib import Path

import requests

from . import channel_config as cfg

SEARCH_URLS = ["https://api.pexels.com/v1/videos/search", "https://api.pexels.com/videos/search"]


def _headers():
    key = os.environ.get("PEXELS_API_KEY", "").strip()
    if not key:
        raise RuntimeError("PEXELS_API_KEY is missing (GitHub secret not set).")
    return {"Authorization": key}


def _search(query, orientation):
    params = {"query": query, "per_page": 20, "size": "medium"}
    if orientation:
        params["orientation"] = orientation
    for url in SEARCH_URLS:
        try:
            r = requests.get(url, headers=_headers(), params=params, timeout=30)
            if r.status_code == 404:
                continue
            r.raise_for_status()
            return r.json().get("videos", [])
        except requests.RequestException as exc:
            print(f"[pexels] search error at {url}: {exc}")
    return []


def _best_file(video):
    files = [f for f in video.get("video_files", []) if f.get("link") and f.get("width") and f.get("height")]
    if not files:
        return None
    portrait = [f for f in files if f["height"] >= f["width"]]
    pool = portrait or files

    def score(f):
        h = max(f["height"], f["width"])
        return abs(h - 1920) + (0 if f.get("file_type") == "video/mp4" else 5000)

    return min(pool, key=score)


def fetch_clip(query, min_seconds, work_dir, used_ids, index):
    queries = [query] + random.sample(cfg.FALLBACK_FOOTAGE_QUERIES, 3)
    for q in queries:
        for orientation in ("portrait", None):
            videos = [v for v in _search(q, orientation) if v.get("id") not in used_ids]
            long_enough = [v for v in videos if v.get("duration", 0) >= min_seconds] or videos
            random.shuffle(long_enough)
            for video in long_enough[:5]:
                f = _best_file(video)
                if not f:
                    continue
                path = Path(work_dir) / f"clip_{index}.mp4"
                try:
                    with requests.get(f["link"], stream=True, timeout=120) as r:
                        r.raise_for_status()
                        with open(path, "wb") as fh:
                            for chunk in r.iter_content(1 << 20):
                                fh.write(chunk)
                except requests.RequestException as exc:
                    print(f"[pexels] download failed: {exc}")
                    continue
                used_ids.add(video["id"])
                user = video.get("user", {}) or {}
                return {
                    "path": str(path),
                    "id": video["id"],
                    "author": user.get("name", "Pexels"),
                    "url": video.get("url", "https://www.pexels.com"),
                }
    raise RuntimeError(f"No footage found for '{query}'")
