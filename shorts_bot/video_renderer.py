"""Assembles footage, narration, music and captions into a 1080x1920 Short."""

import re
import subprocess
from pathlib import Path

FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
W, H, FPS = 1080, 1920, 30

# Shared "look" of the channel: dark, desaturated, vignette, light film grain
LOOK = (
    f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS},"
    "eq=brightness=-0.07:saturation=0.55:contrast=1.08,"
    "colorbalance=bs=0.06:bm=0.03,vignette=PI/4,noise=alls=5:allf=t,setsar=1"
)


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
    """Splits every sentence into 1-3 word chunks timed proportionally to word length."""
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


def write_ass(timeline, series_label, duration, path):
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,Anton,104,&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,0,0,0,0,100,100,1,0,1,7,3,2,60,60,620,1
Style: Label,Anton,58,&H0033B8FF,&H0033B8FF,&H00000000,&H64000000,0,0,0,0,100,100,6,0,1,4,0,8,60,60,150,1
Style: Brand,Anton,40,&H00D0D0D0,&H00D0D0D0,&H00000000,&H64000000,0,0,0,0,100,100,3,0,1,3,0,2,60,60,120,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [
        f"Dialogue: 1,{_ass_time(0)},{_ass_time(duration)},Label,,0,0,0,,{{\\fad(400,400)}}{_clean(series_label)}",
        f"Dialogue: 1,{_ass_time(0)},{_ass_time(duration)},Brand,,0,0,0,,{{\\alpha&H60&}}LANTERN LORE",
    ]
    chunks = caption_chunks(timeline)
    for i, c in enumerate(chunks):
        end = chunks[i + 1]["start"] if i + 1 < len(chunks) and chunks[i + 1]["start"] - c["end"] < 0.35 else c["end"]
        text = _clean(c["text"]).upper()
        pop = "{\\fscx88\\fscy88\\t(0,90,\\fscx100\\fscy100)}"
        lines.append(f"Dialogue: 0,{_ass_time(c['start'])},{_ass_time(end)},Caption,,0,0,0,,{pop}{text}")
    Path(path).write_text(header + "\n".join(lines) + "\n", encoding="utf-8")


def scene_durations(timeline, scene_count, total_duration):
    starts = []
    for s in range(scene_count):
        first = next((t["start"] for t in timeline if t["scene"] == s), None)
        starts.append(first)
    starts[0] = 0.0
    # scenes without sentences (should not happen) get merged into previous
    for i in range(1, scene_count):
        if starts[i] is None:
            starts[i] = starts[i - 1]
    starts.append(total_duration)
    return [max(starts[i + 1] - starts[i], 0.0) for i in range(scene_count)]


def render(clips, timeline, narration_wav, music_wav, duration, series_label, work_dir, out_path):
    work_dir = Path(work_dir)
    durations = scene_durations(timeline, len(clips), duration)
    parts = []
    for i, (clip, dur) in enumerate(zip(clips, durations)):
        if dur < 0.05:
            continue
        part = work_dir / f"scene_{i}.mp4"
        fade = f",fade=t=in:st=0:d=0.3" if i > 0 else ",fade=t=in:st=0:d=0.6"
        _run([
            "ffmpeg", "-y", "-loglevel", "error", "-stream_loop", "-1", "-i", clip["path"],
            "-t", f"{dur:.3f}", "-an", "-vf", LOOK + fade,
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p", str(part)])
        parts.append(part)

    concat_list = work_dir / "scenes.txt"
    concat_list.write_text("".join(f"file '{p.resolve()}'\n" for p in parts), encoding="utf-8")
    visuals = work_dir / "visuals.mp4"
    _run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(concat_list), "-c", "copy", str(visuals)])

    ass = work_dir / "captions.ass"
    write_ass(timeline, series_label, duration, ass)
    ass_arg = str(ass.resolve()).replace("\\", "/").replace(":", "\\:")
    font_arg = str(FONT_DIR.resolve()).replace("\\", "/").replace(":", "\\:")

    fade_out = max(duration - 0.6, 0)
    filter_complex = (
        f"[0:v]ass='{ass_arg}':fontsdir='{font_arg}',fade=t=out:st={fade_out:.2f}:d=0.6[v];"
        "[1:a]aformat=channel_layouts=stereo,aresample=44100[voice];"
        "[2:a]volume=0.22[music];"
        "[voice][music]amix=inputs=2:duration=first:normalize=0,loudnorm=I=-14:TP=-1.5:LRA=11,aresample=44100[a]"
    )
    _run([
        "ffmpeg", "-y", "-loglevel", "error", "-i", str(visuals), "-i", str(narration_wav), "-i", str(music_wav),
        "-filter_complex", filter_complex, "-map", "[v]", "-map", "[a]", "-t", f"{duration:.3f}",
        "-c:v", "libx264", "-preset", "medium", "-crf", "23", "-maxrate", "8M", "-bufsize", "16M", "-pix_fmt", "yuv420p", "-r", str(FPS),
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out_path)])
    print(f"[render] Finished {out_path}")
    return out_path
