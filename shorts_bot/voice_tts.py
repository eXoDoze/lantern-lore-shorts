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


def synthesize(script, work_dir):
    """Returns (wav_path, duration_seconds, timeline). timeline: list of dicts
    {scene, text, start, end} in seconds."""
    work_dir = Path(work_dir)
    engine = "kokoro"
    try:
        _kokoro_engine()
    except Exception as exc:  # noqa: BLE001
        print(f"[tts] Kokoro unavailable ({exc}) -> using Edge-TTS fallback")
        engine = "edge"

    pause = np.zeros(int(cfg.PAUSE_BETWEEN_SENTENCES * SAMPLE_RATE), dtype=np.float32)
    chunks, timeline, cursor = [np.zeros(int(0.25 * SAMPLE_RATE), dtype=np.float32)], [], 0.25

    for scene_idx, scene in enumerate(script["scenes"]):
        for sentence in split_sentences(scene["narration"]):
            if engine == "kokoro":
                try:
                    audio = _synth_kokoro(sentence)
                except Exception as exc:  # noqa: BLE001
                    print(f"[tts] Kokoro failed on a sentence ({exc}); switching to Edge-TTS")
                    engine = "edge"
                    audio = _synth_edge(sentence, work_dir)
            else:
                audio = _synth_edge(sentence, work_dir)
            audio = _trim_silence(audio)
            dur = len(audio) / SAMPLE_RATE
            timeline.append({"scene": scene_idx, "text": sentence, "start": cursor, "end": cursor + dur})
            chunks += [audio, pause]
            cursor += dur + len(pause) / SAMPLE_RATE

    chunks.append(np.zeros(int(0.6 * SAMPLE_RATE), dtype=np.float32))
    full = np.concatenate(chunks)
    peak = float(np.max(np.abs(full))) or 1.0
    full = full / peak * 0.89
    wav_path = work_dir / "narration.wav"
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
