"""Text-to-speech: Kokoro (open model, runs inside GitHub Actions) with Edge-TTS as fallback.

Produces one narration WAV plus exact timings for every sentence (used for captions
and for cutting the footage to the right length).
"""

import asyncio
import os
import re
import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf

from . import channel_config as cfg

SAMPLE_RATE = 24000
MODEL_DIR = Path(os.environ.get("KOKORO_MODEL_DIR", "models/kokoro"))

_kokoro = None


def split_sentences(text):
    parts = re.split(r"(?<=[.!?…])\s+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def _kokoro_engine():
    global _kokoro
    if _kokoro is None:
        from kokoro_onnx import Kokoro
        _kokoro = Kokoro(str(MODEL_DIR / "kokoro-v1.0.onnx"), str(MODEL_DIR / "voices-v1.0.bin"))
    return _kokoro


def _synth_kokoro(sentence):
    samples, sr = _kokoro_engine().create(sentence, voice=cfg.KOKORO_VOICE, speed=cfg.VOICE_SPEED, lang=cfg.KOKORO_LANG)
    samples = np.asarray(samples, dtype=np.float32)
    if sr != SAMPLE_RATE:
        raise RuntimeError(f"Unexpected Kokoro sample rate {sr}")
    return samples


def _synth_edge(sentence, tmp_dir):
    import edge_tts

    mp3 = Path(tmp_dir) / "edge_tmp.mp3"
    wav = Path(tmp_dir) / "edge_tmp.wav"
    asyncio.run(edge_tts.Communicate(sentence, cfg.EDGE_TTS_VOICE, rate="-5%").save(str(mp3)))
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(mp3), "-ac", "1", "-ar", str(SAMPLE_RATE), str(wav)], check=True)
    data, _ = sf.read(str(wav), dtype="float32")
    return data


def _trim_silence(samples, threshold=0.004):
    idx = np.where(np.abs(samples) > threshold)[0]
    if len(idx) == 0:
        return samples
    start = max(idx[0] - int(0.02 * SAMPLE_RATE), 0)
    end = min(idx[-1] + int(0.08 * SAMPLE_RATE), len(samples))
    return samples[start:end]


def _speech_gaps(samples, min_gap=0.09):
    """Midpoints (in seconds) of the silent gaps inside a recording."""
    frame = int(0.01 * SAMPLE_RATE)
    n = len(samples) // frame
    if n == 0:
        return []
    rms = np.sqrt(np.mean(samples[: n * frame].reshape(n, frame) ** 2, axis=1))
    silent = rms < max(float(np.max(rms)) * 0.04, 1e-4)
    gaps, run_start = [], None
    for i, is_silent in enumerate(silent):
        if is_silent and run_start is None:
            run_start = i
        elif not is_silent and run_start is not None:
            if (i - run_start) * 0.01 >= min_gap:
                gaps.append((run_start + i) / 2 * 0.01)
            run_start = None
    return gaps


def _sentence_spans(sentences, samples):
    """Estimates start/end of every sentence inside one recording of a whole scene.
    Uses the real pauses in the audio where possible, character proportions otherwise."""
    total = len(samples) / SAMPLE_RATE
    if len(sentences) == 1:
        return [(0.0, total)]
    weights = [len(s) + 8 for s in sentences]
    expected, acc = [], 0
    for w in weights[:-1]:
        acc += w
        expected.append(total * acc / sum(weights))
    gaps = _speech_gaps(samples)
    bounds, last = [], 0.0
    for exp in expected:
        options = [g for g in gaps if g > last + 0.3]
        best = min(options, key=lambda g: abs(g - exp), default=None)
        if best is not None and abs(best - exp) < max(1.2, 0.25 * total):
            bounds.append(best)
        else:
            bounds.append(max(exp, last + 0.3))
        last = bounds[-1]
    edges = [0.0] + bounds + [total]
    return [(edges[i], edges[i + 1]) for i in range(len(sentences))]


def synthesize(script, work_dir, lead_in=0.08, wav_name="narration.wav"):
    """Returns (wav_path, duration_seconds, timeline). timeline: list of dicts
    {scene, text, start, end} in seconds.

    Each scene is spoken in ONE piece, so the voice keeps a natural flow and
    intonation across sentences (instead of stitching single sentences together)."""
    work_dir = Path(work_dir)
    engine = "kokoro"
    try:
        _kokoro_engine()
    except Exception as exc:  # noqa: BLE001
        print(f"[tts] Kokoro unavailable ({exc}) -> using Edge-TTS fallback")
        engine = "edge"

    scene_pause = np.zeros(int(cfg.PAUSE_BETWEEN_SCENES * SAMPLE_RATE), dtype=np.float32)
    chunks, timeline, cursor = [np.zeros(int(lead_in * SAMPLE_RATE), dtype=np.float32)], [], lead_in

    for scene_idx, scene in enumerate(script["scenes"]):
        text = " ".join(scene["narration"].split())
        sentences = split_sentences(text) or [text]
        if engine == "kokoro":
            try:
                audio = _synth_kokoro(text)
            except Exception as exc:  # noqa: BLE001
                print(f"[tts] Kokoro failed ({exc}); switching to Edge-TTS")
                engine = "edge"
                audio = _synth_edge(text, work_dir)
        else:
            audio = _synth_edge(text, work_dir)
        audio = _trim_silence(audio)
        for sentence, (a, b) in zip(sentences, _sentence_spans(sentences, audio)):
            timeline.append({"scene": scene_idx, "text": sentence, "start": cursor + a, "end": cursor + b})
        chunks += [audio, scene_pause]
        cursor += len(audio) / SAMPLE_RATE + len(scene_pause) / SAMPLE_RATE

    chunks.append(np.zeros(int(0.6 * SAMPLE_RATE), dtype=np.float32))
    full = np.concatenate(chunks)
    peak = float(np.max(np.abs(full))) or 1.0
    full = full / peak * 0.89
    wav_path = work_dir / wav_name
    sf.write(str(wav_path), full, SAMPLE_RATE)
    duration = len(full) / SAMPLE_RATE
    print(f"[tts] Narration via {engine}: {duration:.1f}s")
    return wav_path, duration, timeline


def speed_up(wav_path, timeline, factor):
    """Speeds narration up by `factor` (pitch kept) and rescales the timeline."""
    out = Path(wav_path).with_name("narration_fast.wav")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav_path), "-filter:a", f"atempo={factor:.4f}", str(out)], check=True)
    for t in timeline:
        t["start"] /= factor
        t["end"] /= factor
    data, sr = sf.read(str(out))
    return out, len(data) / sr, timeline
