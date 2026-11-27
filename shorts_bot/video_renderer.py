"""Assembles footage, narration, music and captions into a finished video.

Two formats share the same channel look:
  - "short":    1080x1920 vertical (daily Shorts)
  - "longform": 1920x1080 horizontal (weekly compilation)
"""

import subprocess
from pathlib import Path

FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
FPS = 30

PROFILES = {
    "short": {
        "w": 1080, "h": 1920,
        "caption": "Style: Caption,Anton,104,&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,0,0,0,0,100,100,1,0,1,7,3,2,60,60,620,1",
        "label": "Style: Label,Anton,58,&H0033B8FF,&H0033B8FF,&H00000000,&H64000000,0,0,0,0,100,100,6,0,1,4,0,8,60,60,150,1",
        "brand": "Style: Brand,Anton,40,&H00D0D0D0,&H00D0D0D0,&H00000000,&H64000000,0,0,0,0,100,100,3,0,1,3,0,2,60,60,120,1",
        "max_chars": 16, "max_words": 3, "first_fade": 0.15,
    },
    "longform": {
        "w": 1920, "h": 1080,
        "caption": "Style: Caption,Anton,72,&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,0,0,0,0,100,100,1,0,1,5,2,2,120,120,110,1",
        "label": "Style: Label,Anton,40,&H0033B8FF,&H0033B8FF,&H00000000,&H64000000,0,0,0,0,100,100,5,0,1,3,0,7,70,70,50,1",
        "brand": "Style: Brand,Anton,32,&H00D0D0D0,&H00D0D0D0,&H00000000,&H64000000,0,0,0,0,100,100,3,0,1,2,0,9,70,70,50,1",
        "max_chars": 30, "max_words": 6, "first_fade": 0.5,
    },
}

# Shared "look" of the channel: dark, desaturated, vignette, light film grain
LOOK_TAIL = (
    "eq=brightness=-0.07:saturation=0.55:contrast=1.08,"
    "colorbalance=bs=0.06:bm=0.03,vignette=PI/4,noise=alls=5:allf=t,setsar=1"
)


def look_filter(w, h):
    return f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},fps={FPS}," + LOOK_TAIL


def _run(cmd):
    subprocess.run(cmd, check=True)


def _ass_time(t):
    t = max(t, 0)
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def _clean(text):
    return text.replace("{", "(").replace("}", ")").replace("\\", " ").strip()


def caption_chunks(timeline, max_chars=16, max_words=3):
    """Splits every sentence into short chunks timed proportionally to word length."""
    chunks = []
    for item in timeline:
        words = item["text"].split()
        if not words:
            continue
        groups, cur = [], []
        for w in words:
            if cur and (len(" ".join(cur + [w])) > max_chars or len(cur) >= max_words):
                groups.append(cur)
                cur = []
            cur.append(w)
        if cur:
            groups.append(cur)
        total = sum(len(" ".join(g)) + 1 for g in groups)
        span = item["end"] - item["start"]
        t = item["start"]
        for g in groups:
            d = span * (len(" ".join(g)) + 1) / total
            chunks.append({"start": t, "end": t + d, "text": " ".join(g)})
            t += d
    return chunks


def write_ass(timeline, series_label, duration, path, profile="short"):
    p = PROFILES[profile]
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {p['w']}
PlayResY: {p['h']}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
{p['caption']}
{p['label']}
{p['brand']}

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [
        f"Dialogue: 1,{_ass_time(0)},{_ass_time(duration)},Label,,0,0,0,,{{\\fad(300,400)}}{_clean(series_label)}",
        f"Dialogue: 1,{_ass_time(0)},{_ass_time(duration)},Brand,,0,0,0,,{{\\alpha&H60&}}LANTERN LORE",
    ]
    chunks = caption_chunks(timeline, p["max_chars"], p["max_words"])
    for i, c in enumerate(chunks):
        end = chunks[i + 1]["start"] if i + 1 < len(chunks) and chunks[i + 1]["start"] - c["end"] < 0.35 else c["end"]
        text = _clean(c["text"]).upper()
        pop = "{\\fscx88\\fscy88\\t(0,90,\\fscx100\\fscy100)}" if profile == "short" else ""
        lines.append(f"Dialogue: 0,{_ass_time(c['start'])},{_ass_time(end)},Caption,,0,0,0,,{pop}{text}")
    Path(path).write_text(header + "\n".join(lines) + "\n", encoding="utf-8")


def scene_durations(timeline, scene_count, total_duration):
    starts = []
    for s in range(scene_count):
        first = next((t["start"] for t in timeline if t["scene"] == s), None)
        starts.append(first)
    starts[0] = 0.0
    for i in range(1, scene_count):
        if starts[i] is None:
            starts[i] = starts[i - 1]
    starts.append(total_duration)
    return [max(starts[i + 1] - starts[i], 0.0) for i in range(scene_count)]


def render(clips, timeline, narration_wav, music_wav, duration, series_label, work_dir, out_path,
           profile="short", fade_out_video=True):
    p = PROFILES[profile]
    work_dir = Path(work_dir)
    durations = scene_durations(timeline, len(clips), duration)
    look = look_filter(p["w"], p["h"])
    parts = []
    for i, (clip, dur) in enumerate(zip(clips, durations)):
        if dur < 0.05:
            continue
        part = work_dir / f"scene_{i}.mp4"
        fade = f",fade=t=in:st=0:d={p['first_fade'] if i == 0 else 0.3}"
        _run([
            "ffmpeg", "-y", "-loglevel", "error", "-stream_loop", "-1", "-i", clip["path"],
            "-t", f"{dur:.3f}", "-an", "-vf", look + fade,
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p", str(part)])
        parts.append(part)

    concat_list = work_dir / "scenes.txt"
    concat_list.write_text("".join(f"file '{p_.resolve()}'\n" for p_ in parts), encoding="utf-8")
    visuals = work_dir / "visuals.mp4"
    _run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(concat_list), "-c", "copy", str(visuals)])

    ass = work_dir / "captions.ass"
    write_ass(timeline, series_label, duration, ass, profile)
    ass_arg = str(ass.resolve()).replace("\\", "/").replace(":", "\\:")
    font_arg = str(FONT_DIR.resolve()).replace("\\", "/").replace(":", "\\:")

    vfade = f",fade=t=out:st={max(duration - 0.6, 0):.2f}:d=0.6" if fade_out_video else ""
    filter_complex = (
        f"[0:v]ass='{ass_arg}':fontsdir='{font_arg}'{vfade}[v];"
        "[1:a]aformat=channel_layouts=stereo,aresample=44100[voice];"
        "[2:a]volume=0.22[music];"
        "[voice][music]amix=inputs=2:duration=first:normalize=0,loudnorm=I=-14:TP=-1.5:LRA=11,"
        "aresample=44100,aformat=channel_layouts=stereo[a]"
    )
    preset = "medium" if profile == "short" else "veryfast"
    _run([
        "ffmpeg", "-y", "-loglevel", "error", "-i", str(visuals), "-i", str(narration_wav), "-i", str(music_wav),
        "-filter_complex", filter_complex, "-map", "[v]", "-map", "[a]", "-t", f"{duration:.3f}",
        "-c:v", "libx264", "-preset", preset, "-crf", "23", "-maxrate", "8M", "-bufsize", "16M",
        "-pix_fmt", "yuv420p", "-r", str(FPS),
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-movflags", "+faststart", str(out_path)])
    print(f"[render] Finished {out_path}")
    return out_path


def make_short_thumbnail(scene_video, title, series_label, out_path, work_dir):
    """1080x1920 cover image: a clean frame (no captions) + series label + big title."""
    import textwrap
    lines = textwrap.wrap(_clean(title).upper(), width=14)[:4]
    title_text = "\\N".join(lines)
    ass = Path(work_dir) / "thumbnail_short.ass"
    ass.write_text(f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Label,Anton,62,&H0033B8FF,&H0033B8FF,&H00000000,&H00000000,0,0,0,0,100,100,6,0,1,4,0,8,60,60,260,1
Style: Title,Anton,132,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,1,0,1,9,4,5,70,70,0,1
Style: Brand,Anton,46,&H00D0D0D0,&H00D0D0D0,&H00000000,&H00000000,0,0,0,0,100,100,4,0,1,3,0,2,60,60,300,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.00,0:00:05.00,Label,,0,0,0,,{_clean(series_label)}
Dialogue: 0,0:00:00.00,0:00:05.00,Title,,0,0,0,,{title_text}
Dialogue: 0,0:00:00.00,0:00:05.00,Brand,,0,0,0,,LANTERN LORE
""", encoding="utf-8")
    ass_arg = str(ass.resolve()).replace("\\", "/").replace(":", "\\:")
    font_arg = str(FONT_DIR.resolve()).replace("\\", "/").replace(":", "\\:")
    _run(["ffmpeg", "-y", "-loglevel", "error", "-ss", "1.0", "-i", str(scene_video), "-frames:v", "1",
          "-vf", f"scale=1080:1920,eq=brightness=-0.08,vignette=PI/3.5,ass='{ass_arg}':fontsdir='{font_arg}'",
          "-q:v", "3", str(out_path)])
    return out_path


def brightest_scene(work_dir):
    """Path of the scene clip with the most visible picture (better cover than a nearly black frame)."""
    import numpy as np
    best, best_val = None, -1.0
    for scene in sorted(Path(work_dir).glob("scene_*.mp4")):
        try:
            raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-ss", "1.0", "-i", str(scene), "-frames:v", "1",
                                  "-vf", "scale=27:48,format=gray", "-f", "rawvideo", "-"],
                                 check=True, capture_output=True).stdout
            val = float(np.frombuffer(raw, dtype=np.uint8).mean()) if raw else -1.0
        except (subprocess.CalledProcessError, ValueError):
            continue
        if val > best_val:
            best, best_val = scene, val
    return best or Path(work_dir) / "scene_0.mp4"
