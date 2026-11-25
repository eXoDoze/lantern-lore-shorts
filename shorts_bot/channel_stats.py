"""Learns from the channel's own numbers.

Once a day the bot loads views/likes/comments of its recent videos. From that it
  1. shows better-performing series more often (multiplier 0.5x - 2x), and
  2. tells the writer which titles worked best, as style examples.
"""

import statistics
from datetime import datetime, timedelta, timezone

from . import channel_config as cfg

MIN_AGE_DAYS = 2        # numbers of very fresh videos are not meaningful yet
LOOKBACK_DAYS = 60
MIN_VIDEOS_PER_SERIES = 3


def _parse(date_str):
    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def refresh_statistics(history):
    """Updates history entries in place. Never raises."""
    try:
        from .youtube_uploader import fetch_statistics
        now = datetime.now(timezone.utc)
        ids = [v["video_id"] for v in history["videos"]
               if v.get("video_id") and (d := _parse(v.get("date", ""))) and now - d < timedelta(days=LOOKBACK_DAYS)]
        if not ids:
            return
        stats = fetch_statistics(ids)
        for v in history["videos"]:
            if v.get("video_id") in stats:
                v["stats"] = stats[v["video_id"]]
                v["stats_date"] = now.isoformat(timespec="seconds")
        print(f"[stats] Updated statistics for {len(stats)} videos")
    except Exception as exc:  # noqa: BLE001
        print(f"[stats] Skipped ({exc})")


def _score(v):
    s = v.get("stats") or {}
    # comments and likes are strong signals, views are the base
    return s.get("views", 0) + 20 * s.get("likes", 0) + 50 * s.get("comments", 0)


def _mature(history):
    now = datetime.now(timezone.utc)
    out = []
    for v in history["videos"]:
        d = _parse(v.get("date", ""))
        if v.get("stats") and d and timedelta(days=MIN_AGE_DAYS) <= now - d <= timedelta(days=LOOKBACK_DAYS):
            out.append(v)
    return out


def series_multipliers(history):
    """{series_key: factor}. 1.0 for series without enough data."""
    mature = _mature(history)
    result = {s["key"]: 1.0 for s in cfg.SERIES}
    if len(mature) < 8:
        return result
    overall = statistics.median(_score(v) for v in mature) or 1
    for s in cfg.SERIES:
        scores = [_score(v) for v in mature if v.get("series") == s["key"]]
        if len(scores) >= MIN_VIDEOS_PER_SERIES:
            result[s["key"]] = max(0.5, min(2.0, statistics.median(scores) / overall))
    print("[stats] Series multipliers: " + ", ".join(f"{k}={v:.2f}" for k, v in result.items()))
    return result


def performance_hint(history):
    """A few lines for the writer prompt: best and weakest recent titles."""
    mature = sorted(_mature(history), key=_score, reverse=True)
    if len(mature) < 6:
        return ""
    best = [f'- "{v["title"]}" ({v["stats"]["views"]} views)' for v in mature[:4]]
    worst = [f'- "{v["title"]}" ({v["stats"]["views"]} views)' for v in mature[-3:]]
    return ("Channel data - these recent titles and hooks performed BEST, learn from their style:\n"
            + "\n".join(best)
            + "\nThese performed worst, avoid their style:\n" + "\n".join(worst))
