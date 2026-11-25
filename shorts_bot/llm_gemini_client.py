"""Minimal Gemini API client (free tier).

Model names change over time, so instead of hard-coding one model this client
asks the API which models exist and picks the best available "flash" model.
That keeps the bot running when Google retires older models.
"""

import json
import os
import re
import time

import requests

API_ROOT = "https://generativelanguage.googleapis.com/v1beta"
EXCLUDED_WORDS = ("image", "tts", "audio", "live", "embedding", "vision", "robotics", "computer-use", "native")

_cached_models = None


def _api_key():
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("GEMINI_API_KEY is missing (GitHub secret not set).")
    return key


def _version_of(name):
    m = re.search(r"gemini-(\d+(?:\.\d+)?)", name)
    return float(m.group(1)) if m else 0.0


def list_candidate_models():
    """Return usable text models, best first."""
    global _cached_models
    if _cached_models is not None:
        return _cached_models

    override = os.environ.get("GEMINI_MODEL", "").strip()
    models = []
    try:
        url = f"{API_ROOT}/models"
        params = {"key": _api_key(), "pageSize": 1000}
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        for m in resp.json().get("models", []):
            name = m.get("name", "").replace("models/", "")
            methods = m.get("supportedGenerationMethods", [])
            if "generateContent" not in methods or not name.startswith("gemini-"):
                continue
            if "flash" not in name or any(w in name for w in EXCLUDED_WORDS):
                continue
            models.append(name)
    except Exception as exc:  # noqa: BLE001
        print(f"[llm] Could not list models ({exc}); using built-in fallbacks.")

    def rank(name):
        unstable = ("preview" in name) or ("exp" in name)
        lite = "lite" in name
        # stable before preview, full flash before lite, newer before older
        return (unstable, lite, -_version_of(name), len(name))

    models = sorted(set(models), key=rank)
    fallbacks = ["gemini-flash-latest", "gemini-flash-lite-latest", "gemini-2.5-flash", "gemini-2.5-flash-lite"]
    ordered = ([override] if override else []) + models + [f for f in fallbacks if f not in models]
    _cached_models = ordered
    print(f"[llm] Model candidates: {ordered[:6]}")
    return ordered


def _extract_json(text):
    text = text.strip()
    text = re.sub(r"^```(?:json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = min([i for i in (text.find("{"), text.find("[")) if i >= 0], default=-1)
        if start < 0:
            raise
        end = max(text.rfind("}"), text.rfind("]"))
        return json.loads(text[start:end + 1])


def generate_json(prompt, system=None, temperature=0.9):
    """Send a prompt and return the parsed JSON answer. Tries several models."""
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": temperature, "responseMimeType": "application/json"},
        "safetySettings": [
            {"category": c, "threshold": "BLOCK_ONLY_HIGH"}
            for c in (
                "HARM_CATEGORY_HARASSMENT",
                "HARM_CATEGORY_HATE_SPEECH",
                "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                "HARM_CATEGORY_DANGEROUS_CONTENT",
            )
        ],
    }
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}

    last_error = None
    for model in list_candidate_models():
        for attempt in range(3):
            try:
                resp = requests.post(
                    f"{API_ROOT}/models/{model}:generateContent",
                    params={"key": _api_key()},
                    json=body,
                    timeout=120,
                )
                if resp.status_code in (404, 400) and "not found" in resp.text.lower():
                    last_error = f"{model}: not available"
                    break  # next model
                if resp.status_code in (429, 500, 502, 503, 504):
                    last_error = f"{model}: HTTP {resp.status_code}"
                    time.sleep(15 * (attempt + 1))
                    continue
                resp.raise_for_status()
                data = resp.json()
                parts = data["candidates"][0]["content"]["parts"]
                text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
                return _extract_json(text)
            except (KeyError, IndexError, json.JSONDecodeError) as exc:
                last_error = f"{model}: unusable answer ({exc})"
                time.sleep(3)
                continue
            except requests.RequestException as exc:
                last_error = f"{model}: {exc}"
                time.sleep(5)
                continue
    raise RuntimeError(f"All Gemini models failed. Last error: {last_error}")
