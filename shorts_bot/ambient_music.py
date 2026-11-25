"""Background music.

If you put your own royalty-free tracks (e.g. from the YouTube Audio Library) into
assets/music/, one of them is used at random. Otherwise a dark ambient drone is
generated from scratch with ffmpeg - it is 100 % original, so there is never a
copyright claim.
"""

import random
import subprocess
from pathlib import Path

MUSIC_DIR = Path(__file__).resolve().parent.parent / "assets" / "music"
ROOT_NOTES = [41.2, 43.65, 46.25, 49.0, 55.0, 61.74]  # low E, F, F#, G, A, B


def _own_tracks():
    if not MUSIC_DIR.exists():
        return []
    return [p for p in MUSIC_DIR.iterdir() if p.suffix.lower() in (".mp3", ".wav", ".m4a", ".ogg")]


def make_background(duration, work_dir):
    out = Path(work_dir) / "music.wav"
    tracks = _own_tracks()
    if tracks:
        track = random.choice(tracks)
        print(f"[music] Using own track {track.name}")
        subprocess.run([
            "ffmpeg", "-y", "-loglevel", "error", "-stream_loop", "-1", "-i", str(track),
            "-t", f"{duration:.2f}", "-ac", "2", "-ar", "44100", str(out)], check=True)
        return out

    f = random.choice(ROOT_NOTES)
    fifth, octave, minor3 = f * 1.4983, f * 2, f * 2.3784
    l1, l2, l3 = (round(random.uniform(0.03, 0.12), 3) for _ in range(3))
    expr = (
        f"0.30*sin(2*PI*{f}*t)*(0.65+0.35*sin(2*PI*{l1}*t))"
        f"+0.16*sin(2*PI*{fifth}*t+0.8*sin(2*PI*{l2}*t))"
        f"+0.10*sin(2*PI*{octave}*t)*(0.5+0.5*sin(2*PI*{l3}*t))"
        f"+0.05*sin(2*PI*{minor3}*t)*(0.5+0.5*sin(2*PI*{l1 * 1.7:.3f}*t))"
    )
    fade_out_start = max(duration - 2.5, 0)
    filter_graph = (
        f"aevalsrc='{expr}':s=44100:d={duration:.2f}[drone];"
        f"anoisesrc=color=brown:amplitude=0.25:d={duration:.2f}:r=44100,lowpass=f=320[wind];"
        "[drone][wind]amix=inputs=2:weights='1 0.6':normalize=0,"
        "aecho=0.8:0.7:400|900:0.25|0.15,lowpass=f=1800,"
        f"afade=t=in:d=2,afade=t=out:st={fade_out_start:.2f}:d=2.5,"
        "aformat=channel_layouts=stereo[out]"
    )
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error", "-filter_complex", filter_graph, "-map", "[out]",
        "-ar", "44100", str(out)], check=True)
    print(f"[music] Generated ambient drone (root {f} Hz)")
    return out
