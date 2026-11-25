"""Main entry point: topic -> script -> voice -> footage -> render -> upload -> history.

Usage:
    python -m shorts_bot.run_pipeline            # make + upload one Short
    python -m shorts_bot.run_pipeline --no-upload  # test run, video only saved in output/
    python -m shorts_bot.run_pipeline --series appalachian
"""

import argparse
import os
import shutil
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

from . import channel_config as cfg
from .ambient_music import make_background
from .footage_pexels import fetch_clip
from .story_writer import write_script
from .topic_planner import find_new_topic, load_history, pick_series, save_history, uploads_today
from .video_renderer import render
from .voice_tts import speed_up, synthesize

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "output"


def build_description(script, series, clips):
    authors = sorted({c["author"] for c in clips})
    if series["fiction"]:
        note = "An original fictional story, told for entertainment."
    else:
        note = "Based on folklore, legends and unverified accounts - retold for entertainment, not presented as proven fact."
    hashtags = " ".join(cfg.BASE_HASHTAGS + series.get("hashtags", []))
    return (
        f"{script.get('description', '').strip()}\n\n"
        f"{note}\n\n"
        f"{cfg.CHANNEL_NAME} - {cfg.CHANNEL_TAGLINE} New legends every day.\n\n"
        f"Narration: AI voice. Footage: Pexels ({', '.join(authors)}). Music: original.\n\n"
        f"{hashtags}"
    )


def write_summary(lines):
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")


def make_one(history, series_key, upload_enabled, work_dir):
    series = pick_series(history, series_key)
    print(f"[main] Series: {series['label']}")
    topic = find_new_topic(series, history)
    if topic is None:
        print("[main] No fresh topic found in this series -> switching to Campfire Tales")
        series = next(s for s in cfg.SERIES if s["fiction"])
        topic = find_new_topic(series, history)
        if topic is None:
            raise RuntimeError("No new topic could be found.")
    print(f"[main] Topic: {topic['subject']} - {topic['angle']}")

    script, feedback = None, ""
    for _ in range(3):
        script = write_script(series, topic, feedback)
        wav, duration, timeline = synthesize(script, work_dir)
        if duration <= cfg.MAX_DURATION_SECONDS:
            break
        factor = duration / cfg.MAX_DURATION_SECONDS
        if factor <= cfg.MAX_SPEEDUP:
            wav, duration, timeline = speed_up(wav, timeline, factor + 0.005)
            break
        feedback = f"The previous version took {duration:.0f} seconds to read - it must be clearly shorter (max {cfg.MAX_WORDS - 15} words)."
        print(f"[main] Narration too long ({duration:.1f}s), rewriting shorter")
    else:
        raise RuntimeError("Narration stayed too long after 3 attempts.")

    used_ids = set()
    for v in history["videos"][-300:]:
        used_ids.update(v.get("pexels_ids", []))
    clips = []
    for i, scene in enumerate(script["scenes"]):
        scene_len = sum(t["end"] - t["start"] for t in timeline if t["scene"] == i) + 1
        clips.append(fetch_clip(scene["footage_query"], scene_len, work_dir, used_ids, i))

    music = make_background(duration, work_dir)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    OUTPUT_DIR.mkdir(exist_ok=True)
    out_path = OUTPUT_DIR / f"lantern_lore_{stamp}.mp4"
    render(clips, timeline, wav, music, duration, series["label"], work_dir, out_path)

    description = build_description(script, series, clips)
    tags = list(dict.fromkeys(script.get("tags", []) + ["legends", "folklore", "scary stories", "shorts"]))[:15]

    video_id, status = None, "not uploaded (test run)"
    if upload_enabled:
        from .youtube_uploader import upload
        video_id, status = upload(out_path, script["title"], description, tags)

    entry = {
        "date": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "series": series["key"],
        "subject": topic["subject"],
        "title": script["title"],
        "duration": round(duration, 1),
        "video_id": video_id,
        "privacy": status,
        "pexels_ids": [c["id"] for c in clips],
    }
    write_summary([
        f"## {script['title']}",
        f"- Serie: {series['label']}",
        f"- Thema: {topic['subject']}",
        f"- Laenge: {duration:.1f} s",
        f"- Upload: {'https://youtube.com/shorts/' + video_id if video_id else status}",
        "",
        "```",
        " ".join(s["narration"] for s in script["scenes"]),
        "```",
    ])
    return entry


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-upload", action="store_true")
    parser.add_argument("--series", default=os.environ.get("FORCE_SERIES", "").strip() or None)
    args = parser.parse_args()

    if os.environ.get("LL_PAUSED", "").strip().lower() in ("1", "true", "yes", "ja"):
        print("[main] Bot is paused (repository variable LL_PAUSED). Nothing to do.")
        return 0

    upload_enabled = not args.no_upload
    history = load_history()
    try:
        per_day = int(os.environ.get("SHORTS_PER_DAY") or cfg.DEFAULT_SHORTS_PER_DAY)
    except ValueError:
        per_day = cfg.DEFAULT_SHORTS_PER_DAY
    if upload_enabled and uploads_today(history) >= per_day:
        print(f"[main] Already {per_day} Shorts uploaded today. Skipping.")
        return 0

    last_error = None
    for attempt in range(1, 4):
        work_dir = ROOT / "build" / f"attempt_{attempt}"
        shutil.rmtree(work_dir, ignore_errors=True)
        work_dir.mkdir(parents=True)
        try:
            entry = make_one(history, args.series, upload_enabled, work_dir)
            if upload_enabled:
                history["videos"].append(entry)
                save_history(history)
            print("[main] Done.")
            return 0
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            traceback.print_exc()
            print(f"[main] Attempt {attempt} failed: {exc}")
            if "Missing GitHub secrets" in str(exc) or "is missing" in str(exc):
                break
    print(f"::error::No Short could be produced: {last_error}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
