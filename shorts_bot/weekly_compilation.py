"""Weekly long video: the best Shorts of the last weeks, re-told in 16:9 as one calm session.

Why: long videos earn watch hours (Shorts-feed hours do not count for the Partner Program)
and long videos pay much more per view than Shorts.

Usage:
    python -m shorts_bot.weekly_compilation              # build + upload
    python -m shorts_bot.weekly_compilation --no-upload  # test run, video only in output/
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import channel_config as cfg
from .ambient_music import make_background
from .channel_stats import refresh_statistics, _score
from .footage_stock import choose_clips
from .llm_gemini_client import generate_json
from .playlist_manager import COMPILATION_KEY, add_video as add_to_playlist
from .topic_planner import load_history, save_history
from .video_renderer import FONT_DIR, FPS, _clean, render
from .voice_tts import synthesize

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "output"
W, H = 1920, 1080
MIN_STORIES = 6
MAX_STORIES = 12
LOOKBACK_DAYS = 42
CARD_SECONDS = 3.0


def _run(cmd):
    subprocess.run(cmd, check=True)


def _duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
                         check=True, capture_output=True, text=True).stdout
    return float(json.loads(out)["format"]["duration"])


def _timestamp(seconds):
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


# Series that fit together in one long video. Each week the group with the most
# not-yet-compiled stories wins, so every theme gets its turn.
THEME_GROUPS = [
    {"key": "appalachian", "series": ["appalachian"], "theme": "Appalachian legends and mountain folklore"},
    {"key": "cryptids", "series": ["cryptids"], "theme": "cryptid sightings and strange creatures"},
    {"key": "haunted_unexplained", "series": ["haunted_places", "unexplained_history"],
     "theme": "haunted places and unexplained historical mysteries"},
    {"key": "folklore_superstitions", "series": ["world_folklore", "old_superstitions"],
     "theme": "folklore and old superstitions from around the world"},
    {"key": "campfire", "series": ["campfire_tales"], "theme": "original campfire horror stories (fiction)"},
]


def pick_stories(history):
    """Returns (stories, theme_text). Prefers one theme group; mixed only as fallback."""
    compiled = {vid for c in history.get("compilations", []) for vid in c.get("video_ids", [])}
    now = datetime.now(timezone.utc)
    pool = []
    for v in history["videos"]:
        try:
            age = now - datetime.fromisoformat(v["date"])
        except (KeyError, ValueError):
            continue
        if v.get("scenes") and v.get("video_id") and v["video_id"] not in compiled and age <= timedelta(days=LOOKBACK_DAYS):
            pool.append(v)

    last_group = (history.get("compilations") or [{}])[-1].get("theme_group")
    best = None
    for g in THEME_GROUPS:
        members = [v for v in pool if v.get("series") in g["series"]]
        # small bonus for a different theme than last week, so themes alternate
        rank = len(members) + (0 if g["key"] != last_group else -3)
        if len(members) >= MIN_STORIES and (best is None or rank > best[0]):
            best = (rank, g, members)
    if best:
        _, group, members = best
        members.sort(key=_score, reverse=True)
        print(f"[weekly] Theme of the week: {group['theme']} ({len(members)} stories available)")
        return members[:MAX_STORIES], group
    pool.sort(key=_score, reverse=True)
    print("[weekly] No theme has enough stories yet - using a mixed collection")
    return pool[:MAX_STORIES], {"key": "mixed", "theme": "a mix of legends, folklore and eerie tales"}


def plan_texts(stories, group):
    titles = "\n".join(f"- {s['title']}" for s in stories)
    prompt = f"""You write for the YouTube channel "{cfg.CHANNEL_NAME}" ({cfg.CHANNEL_TAGLINE}).
This week's long video collects these {len(stories)} stories about {group['theme']} into one calm storytelling session
that people listen to in the evening or to fall asleep:
{titles}

Return JSON:
{{"title": "searchable, intriguing title, max 80 characters, mention the number of stories, no emojis, e.g. '12 Appalachian Legends to Hear Before You Sleep'",
 "intro": "spoken welcome, 2-3 calm sentences, max 45 words, invite the viewer to get comfortable, no request to subscribe",
 "outro": "spoken goodbye, 2 calm sentences, max 35 words, ask viewers which story unsettled them most",
 "description": "3 sentences for the YouTube description",
 "thumbnail_text": "2 to 4 words in capitals for the thumbnail, e.g. 'DON'T WHISTLE HERE'",
 "tags": ["10 to 15 lowercase tags"]}}"""
    try:
        data = generate_json(prompt, temperature=0.8)
        if all(data.get(k) for k in ("title", "intro", "outro")):
            return data
    except Exception as exc:  # noqa: BLE001
        print(f"[weekly] Text generation failed ({exc}), using fallback texts")
    return {
        "title": f"{len(stories)} Legends to Hear Before You Sleep | {cfg.CHANNEL_NAME}",
        "intro": "Welcome back to Lantern Lore. Turn the lights down, get comfortable, and listen. "
                 f"Tonight there are {len(stories)} legends waiting in the dark.",
        "outro": "That was this week's collection. Which story unsettled you the most? Goodnight, and keep the lantern burning.",
        "description": "This week's legends from Lantern Lore, collected into one calm storytelling session.",
        "thumbnail_text": "LEGENDS AFTER DARK",
        "tags": ["legends", "folklore", "scary stories", "sleep stories", "campfire stories"],
    }


def _card(title, chapter_label, path):
    """3-second title card on a dark fog background."""
    ass = Path(path).with_suffix(".ass")
    ass.write_text(f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Chapter,Anton,44,&H0033B8FF,&H0033B8FF,&H00000000,&H00000000,0,0,0,0,100,100,8,0,1,2,0,5,100,100,0,1
Style: Title,Anton,96,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,1,0,1,4,2,5,140,140,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.00,0:00:{CARD_SECONDS:05.2f},Chapter,,0,0,0,,{{\\pos({W // 2},{H // 2 - 120})\\fad(300,300)}}{_clean(chapter_label).upper()}
Dialogue: 0,0:00:00.00,0:00:{CARD_SECONDS:05.2f},Title,,0,0,0,,{{\\pos({W // 2},{H // 2 + 20})\\fad(300,300)}}{_clean(title).upper()}
""", encoding="utf-8")
    ass_arg = str(ass.resolve()).replace("\\", "/").replace(":", "\\:")
    font_arg = str(FONT_DIR.resolve()).replace("\\", "/").replace(":", "\\:")
    vf = (f"format=yuv420p,noise=c0s=100:c0f=t,tmix=frames=20,gblur=sigma=1.2,scale={W}:{H}:flags=bicubic,"
          f"eq=contrast=2.0:brightness=-0.2,lutyuv=u=126:v=130,ass='{ass_arg}':fontsdir='{font_arg}',format=yuv420p")
    _run(["ffmpeg", "-y", "-loglevel", "error",
          "-f", "lavfi", "-i", f"color=c=0x606060:s=48x27:r={FPS}:d={CARD_SECONDS}",
          "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=stereo:d={CARD_SECONDS}",
          "-vf", vf, "-map", "0:v", "-map", "1:a", "-t", f"{CARD_SECONDS}",
          "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p", "-r", str(FPS),
          "-c:a", "aac", "-b:a", "192k", "-ar", "44100", str(path)])


def _narrated_segment(scenes, label, work_dir, out_path, used_ids):
    work_dir.mkdir(parents=True, exist_ok=True)
    script = {"scenes": scenes}
    wav, duration, timeline = synthesize(script, work_dir, lead_in=0.6)
    lengths = [sum(t["end"] - t["start"] for t in timeline if t["scene"] == i) + 1.5 for i in range(len(scenes))]
    clips = choose_clips(scenes, lengths, work_dir, used_ids, landscape=True)
    music = make_background(duration, work_dir)
    render(clips, timeline, wav, music, duration, label, work_dir, out_path, profile="longform")
    return clips


def _thumbnail(source_video, text, path, work_dir):
    ass = Path(work_dir) / "thumbnail.ass"
    ass.write_text(f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1280
PlayResY: 720
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Big,Anton,118,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,2,0,1,8,4,1,60,60,70,1
Style: Brand,Anton,46,&H0033B8FF,&H0033B8FF,&H00000000,&H00000000,0,0,0,0,100,100,6,0,1,4,0,7,60,60,50,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.00,0:00:05.00,Brand,,0,0,0,,{cfg.CHANNEL_NAME.upper()}
Dialogue: 0,0:00:00.00,0:00:05.00,Big,,0,0,0,,{_clean(text).upper()}
""", encoding="utf-8")
    ass_arg = str(ass.resolve()).replace("\\", "/").replace(":", "\\:")
    font_arg = str(FONT_DIR.resolve()).replace("\\", "/").replace(":", "\\:")
    seek = min(4.0, _duration(source_video) / 2)
    _run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{seek:.2f}", "-i", str(source_video), "-frames:v", "1",
          "-vf", f"scale=1280:720,eq=brightness=-0.05:contrast=1.15,vignette=PI/3.5,ass='{ass_arg}':fontsdir='{font_arg}'",
          "-q:v", "3", str(path)])


def build(history, upload_enabled):
    stories, group = pick_stories(history)
    if len(stories) < MIN_STORIES:
        print(f"[weekly] Only {len(stories)} new stories available (need {MIN_STORIES}). Skipping this week.")
        return None
    print(f"[weekly] Building compilation with {len(stories)} stories")
    texts = plan_texts(stories, group)

    work = ROOT / "build" / "weekly"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    used_ids = set()
    for v in history["videos"][-150:]:
        used_ids.update(v.get("footage_ids", []))

    parts, chapters, credits, cursor = [], [], set(), 0.0

    intro = work / "00_intro.mp4"
    clips = _narrated_segment([{"narration": texts["intro"], "footage_query": "lantern dark night"}],
                              cfg.CHANNEL_NAME.upper(), work / "intro", intro, used_ids)
    parts.append(intro)
    chapters.append((0.0, "Welcome"))
    cursor += _duration(intro)

    series_labels = {s["key"]: s["label"] for s in cfg.SERIES}
    for n, story in enumerate(stories, start=1):
        card = work / f"{n:02d}_card.mp4"
        _card(story["title"], f"Story {n}", card)
        seg = work / f"{n:02d}_story.mp4"
        clips = _narrated_segment(story["scenes"], series_labels.get(story["series"], cfg.CHANNEL_NAME.upper()),
                                  work / f"story_{n:02d}", seg, used_ids)
        credits.update(f'{c["author"]} ({c["source"]})' for c in clips if c["source"] != "generated")
        chapters.append((cursor, story["title"]))
        parts += [card, seg]
        cursor += _duration(card) + _duration(seg)

    outro = work / "99_outro.mp4"
    _narrated_segment([{"narration": texts["outro"], "footage_query": "candle flame dark"}],
                      cfg.CHANNEL_NAME.upper(), work / "outro", outro, used_ids)
    parts.append(outro)
    chapters.append((cursor, "Goodnight"))

    concat = work / "parts.txt"
    concat.write_text("".join(f"file '{p.resolve()}'\n" for p in parts), encoding="utf-8")
    OUTPUT_DIR.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    final = OUTPUT_DIR / f"lantern_lore_weekly_{stamp}.mp4"
    _run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(concat),
          "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p", "-r", str(FPS),
          "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-movflags", "+faststart", str(final)])
    total = _duration(final)
    print(f"[weekly] Finished {final} ({total / 60:.1f} min)")

    thumb = OUTPUT_DIR / f"lantern_lore_weekly_{stamp}.jpg"
    # frame from the first story's footage, before captions are burned in
    _thumbnail(work / "story_01" / "scene_0.mp4", texts.get("thumbnail_text") or "LEGENDS AFTER DARK", thumb, work)

    chapter_lines = "\n".join(f"{_timestamp(t)} {title}" for t, title in chapters)
    short_links = "\n".join(f"- {s['title']}: https://youtube.com/shorts/{s['video_id']}" for s in stories)
    description = (
        f"{texts.get('description', '').strip()}\n\n"
        f"Chapters:\n{chapter_lines}\n\n"
        "Stories are based on folklore, legends and unverified accounts and retold for entertainment; "
        "Campfire Tales are original fiction.\n\n"
        f"The original Shorts:\n{short_links}\n\n"
        f"Narration: AI voice. Footage: {', '.join(sorted(credits)) or 'original'}. Music: original.\n\n"
        "#legends #folklore #scarystories #sleepstories"
    )
    tags = list(dict.fromkeys([str(t)[:40] for t in texts.get("tags", [])] + ["legends", "folklore", "sleep stories"]))[:15]

    entry = {"date": datetime.now(timezone.utc).isoformat(timespec="seconds"), "title": texts["title"],
             "video_ids": [s["video_id"] for s in stories], "theme_group": group["key"], "duration_min": round(total / 60, 1), "youtube_id": None}
    if upload_enabled:
        from .youtube_uploader import set_thumbnail, upload
        vid, _ = upload(final, texts["title"], description, tags)
        set_thumbnail(vid, thumb)
        add_to_playlist(COMPILATION_KEY, vid)
        entry["youtube_id"] = vid

    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write(f"## {texts['title']}\n- Laenge: {total / 60:.1f} min\n- Geschichten: {len(stories)}\n"
                     f"- Upload: {'https://youtube.com/watch?v=' + entry['youtube_id'] if entry['youtube_id'] else 'Testlauf, nicht hochgeladen'}\n\n"
                     f"```\n{chapter_lines}\n```\n")
    return entry


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-upload", action="store_true")
    args = parser.parse_args()
    if os.environ.get("LL_PAUSED", "").strip().lower() in ("1", "true", "yes", "ja"):
        print("[weekly] Bot is paused (repository variable LL_PAUSED).")
        return 0
    upload_enabled = not args.no_upload
    history = load_history()
    if upload_enabled:
        refresh_statistics(history)
    try:
        entry = build(history, upload_enabled)
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        print(f"::error::Weekly compilation failed: {exc}")
        return 1
    if entry and upload_enabled:
        history.setdefault("compilations", []).append(entry)
        save_history(history)
    return 0


if __name__ == "__main__":
    sys.exit(main())
