"""Free stock footage: Pixabay (main), Pexels (optional), generated fog as last resort.

Whatever happens, this module always returns a usable clip, so a missing or broken
footage service never stops the daily upload.
"""

import os
import random
import subprocess
from pathlib import Path

import requests

from . import channel_config as cfg

PIXABAY_URL = "https://pixabay.com/api/videos/"
PEXELS_URLS = ["https://api.pexels.com/v1/videos/search", "https://api.pexels.com/videos/search"]


# ------------------------------------------------------------------ Pixabay
def _pixabay_candidates(query):
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
        pool = portrait or files
        best = min(pool, key=lambda f: abs(max(f.get("height", 0), f.get("width", 0)) - 1920))
        out.append({
            "uid": f"pixabay:{h['id']}",
            "link": best["url"],
            "duration": h.get("duration", 0),
            "portrait": bool(portrait),
            "author": h.get("user", "Pixabay"),
            "source": "Pixabay",
        })
    return out


# ------------------------------------------------------------------ Pexels (only if a key exists)
def _pexels_candidates(query):
    key = os.environ.get("PEXELS_API_KEY", "").strip()
    if not key:
        return []
    for url in PEXELS_URLS:
        try:
            r = requests.get(url, headers={"Authorization": key},
                             params={"query": query, "per_page": 20, "orientation": "portrait"}, timeout=30)
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
def _generated_fog(seconds, path):
    """Dark drifting fog made from noise - original, needs no service at all."""
    u, v = random.choice([(124, 130), (132, 124), (126, 126), (130, 132)])  # slight colour tint
    vf = (
        "format=yuv420p,noise=c0s=100:c0f=t,tmix=frames=20,gblur=sigma=1.2,"
        f"scale=1080:1920:flags=bicubic,eq=contrast=2.2:brightness=-0.12,lutyuv=u={u}:v={v},format=yuv420p"
    )
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "lavfi", "-i", f"color=c=0x606060:s=27x48:r=30:d={seconds + 1:.2f}",
        "-vf", vf, "-c:v", "libx264", "-preset", "veryfast", "-crf", "24", str(path)], check=True)


def _download(link, path):
    with requests.get(link, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(path, "wb") as fh:
            for chunk in r.iter_content(1 << 20):
                fh.write(chunk)


def fetch_clip(query, min_seconds, work_dir, used_ids, index):
    path = Path(work_dir) / f"clip_{index}.mp4"
    queries = [query] + random.sample(cfg.FALLBACK_FOOTAGE_QUERIES, 3)
    for q in queries:
        candidates = [c for c in _pixabay_candidates(q) + _pexels_candidates(q) if c["uid"] not in used_ids]
        if not candidates:
            continue
        # prefer clips that are long enough, then portrait ones
        candidates.sort(key=lambda c: (c["duration"] < min_seconds, not c["portrait"], random.random()))
        for c in candidates[:5]:
            try:
                _download(c["link"], path)
            except requests.RequestException as exc:
                print(f"[footage] download failed: {exc}")
                continue
            used_ids.add(c["uid"])
            return {"path": str(path), "id": c["uid"], "author": c["author"], "source": c["source"]}
    print(f"[footage] No stock clip for '{query}' -> generated fog background")
    _generated_fog(min_seconds, path)
    return {"path": str(path), "id": f"fog:{index}", "author": "original", "source": "generated"}
