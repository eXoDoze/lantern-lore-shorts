"""Keeps one public playlist per series (plus one for the weekly compilations).

Playlist IDs are remembered in data/playlists.json so each playlist is created only once.
"""

import json
from pathlib import Path

from . import channel_config as cfg

PLAYLIST_FILE = Path(__file__).resolve().parent.parent / "data" / "playlists.json"
COMPILATION_KEY = "weekly_compilations"


def _load():
    if PLAYLIST_FILE.exists():
        return json.loads(PLAYLIST_FILE.read_text(encoding="utf-8"))
    return {}


def _save(data):
    PLAYLIST_FILE.parent.mkdir(parents=True, exist_ok=True)
    PLAYLIST_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _title_and_description(key):
    if key == COMPILATION_KEY:
        return (f"Legends to Fall Asleep To | {cfg.CHANNEL_NAME}",
                "Every week the best short legends of the channel, collected into one long, calm storytelling session.")
    series = next(s for s in cfg.SERIES if s["key"] == key)
    pretty = series["label"].title()
    return (f"{pretty} | {cfg.CHANNEL_NAME}",
            f"{series['brief']}\n\n{cfg.CHANNEL_NAME} - {cfg.CHANNEL_TAGLINE}")


def add_video(key, video_id):
    """Adds a video to the playlist of `key` (series key or COMPILATION_KEY). Never raises."""
    try:
        from .youtube_uploader import add_to_playlist, create_playlist
        data = _load()
        if key not in data:
            title, desc = _title_and_description(key)
            data[key] = create_playlist(title, desc)
            _save(data)
        if add_to_playlist(data[key], video_id) == "notfound":
            # playlist was deleted by hand -> recreate once
            title, desc = _title_and_description(key)
            data[key] = create_playlist(title, desc)
            _save(data)
            add_to_playlist(data[key], video_id)
    except Exception as exc:  # noqa: BLE001
        print(f"[playlist] Skipped ({exc})")
