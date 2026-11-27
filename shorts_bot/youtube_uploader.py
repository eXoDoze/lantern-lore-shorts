"""Everything that talks to YouTube: upload, playlists, thumbnails, statistics.

Upload needs only the youtube.upload permission. Playlists and statistics need the
broader "youtube" permission; if the refresh token does not have it yet, those
extras are skipped with a warning and uploading keeps working.
"""

import os
import socket
import ssl
import time

import httplib2

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from . import channel_config as cfg

_client_cache = None


def get_client(fresh=False):
    """fresh=True builds a new client with a new network connection. Used before uploads:
    a connection opened earlier (e.g. for statistics) is often closed by Google during the
    minutes of rendering, which then fails with SSLEOFError."""
    global _client_cache
    if _client_cache is not None and not fresh:
        return _client_cache
    missing = [k for k in ("YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN") if not os.environ.get(k)]
    if missing:
        raise RuntimeError(f"Missing GitHub secrets: {', '.join(missing)}")
    # no explicit scopes: the token keeps exactly the permissions it was granted
    creds = Credentials(
        None,
        refresh_token=os.environ["YT_REFRESH_TOKEN"].strip(),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.environ["YT_CLIENT_ID"].strip(),
        client_secret=os.environ["YT_CLIENT_SECRET"].strip(),
    )
    creds.refresh(Request())
    _client_cache = build("youtube", "v3", credentials=creds, cache_discovery=False)
    return _client_cache


def _permission_problem(exc):
    return isinstance(exc, HttpError) and exc.resp.status in (401, 403)


NETWORK_ERRORS = (ssl.SSLError, ConnectionError, socket.timeout, TimeoutError, OSError,
                  httplib2.HttpLib2Error)


def _upload_once(video_path, body):
    youtube = get_client(fresh=True)
    media = MediaFileUpload(str(video_path), mimetype="video/mp4", chunksize=4 * 1024 * 1024, resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    response, retries = None, 0
    while response is None:
        try:
            # num_retries makes the client library itself retry short network hiccups
            _, response = request.next_chunk(num_retries=5)
        except HttpError as exc:
            if exc.resp.status in (500, 502, 503, 504) and retries < 6:
                retries += 1
                time.sleep(10 * retries)
                continue
            raise
        except NETWORK_ERRORS as exc:
            if retries < 6:
                retries += 1
                print(f"[upload] Connection problem ({exc.__class__.__name__}), resuming in {10 * retries}s ...")
                time.sleep(10 * retries)
                continue
            raise
    return response


def upload(video_path, title, description, tags, category_id=None):
    body = {
        "snippet": {
            "title": title[:100],
            "description": description[:4900],
            "tags": tags,
            "categoryId": category_id or cfg.YOUTUBE_CATEGORY_ID,
            "defaultLanguage": "en",
            "defaultAudioLanguage": "en",
        },
        "status": {
            "privacyStatus": cfg.PRIVACY_STATUS,
            "selfDeclaredMadeForKids": False,
            "containsSyntheticMedia": cfg.DECLARE_SYNTHETIC_MEDIA,
        },
    }
    # Upload the SAME finished video up to 3 times before giving up - never re-create the video for this.
    last_exc = None
    for attempt in range(1, 4):
        try:
            response = _upload_once(video_path, body)
            break
        except HttpError:
            raise
        except NETWORK_ERRORS as exc:
            last_exc = exc
            print(f"[upload] Upload attempt {attempt} failed ({exc.__class__.__name__}); starting a fresh upload in 30s")
            time.sleep(30)
    else:
        raise RuntimeError(f"Upload failed after 3 attempts: {last_exc}")

    video_id = response["id"]
    status = response.get("status", {}).get("privacyStatus")
    print(f"[upload] Uploaded https://youtube.com/watch?v={video_id} (status: {status})")
    if cfg.PRIVACY_STATUS == "public" and status != "public":
        print("::warning::YouTube set the video to private. The Google Cloud project probably needs the "
              "free YouTube API audit (see README, section 'Videos bleiben privat').")
    return video_id, status


def create_playlist(title, description):
    youtube = get_client()
    resp = youtube.playlists().insert(part="snippet,status", body={
        "snippet": {"title": title[:150], "description": description[:4900], "defaultLanguage": "en"},
        "status": {"privacyStatus": "public"},
    }).execute()
    print(f"[playlist] Created playlist '{title}' ({resp['id']})")
    return resp["id"]


def add_to_playlist(playlist_id, video_id):
    # right after creating a playlist or uploading, YouTube sometimes answers 409/503
    # ("operation was aborted") for a few seconds -> wait and retry
    for attempt in range(4):
        try:
            get_client().playlistItems().insert(part="snippet", body={
                "snippet": {"playlistId": playlist_id, "resourceId": {"kind": "youtube#video", "videoId": video_id}},
            }).execute()
            print(f"[playlist] Added {video_id} to {playlist_id}")
            return "ok"
        except HttpError as exc:
            if exc.resp.status == 404:
                return "notfound"
            if _permission_problem(exc):
                print("::warning::Playlist skipped - the refresh token lacks the 'youtube' permission (see README).")
                return "error"
            if exc.resp.status in (409, 500, 503) and attempt < 3:
                time.sleep(10 * (attempt + 1))
                continue
            print(f"[playlist] Could not add video: {exc}")
            return "error"
        except NETWORK_ERRORS as exc:
            if attempt < 3:
                time.sleep(10)
                continue
            print(f"[playlist] Could not add video: {exc}")
            return "error"
    return "error"


def wait_until_processed(video_id, max_minutes=8):
    """YouTube accepts a custom thumbnail for a Short only after processing has finished."""
    deadline = time.time() + max_minutes * 60
    while time.time() < deadline:
        try:
            items = get_client().videos().list(part="processingDetails", id=video_id).execute().get("items", [])
            status = items[0]["processingDetails"].get("processingStatus") if items else None
        except (HttpError, *NETWORK_ERRORS) as exc:
            print(f"[upload] Could not read processing status ({exc})")
            return False
        if status == "succeeded":
            return True
        if status in ("failed", "terminated"):
            return False
        time.sleep(20)
    print("[upload] Processing took too long - thumbnail skipped this time")
    return False


def set_thumbnail(video_id, image_path):
    """Returns True on success, False if YouTube refused (e.g. channel not eligible yet)."""
    try:
        get_client().thumbnails().set(videoId=video_id, media_body=MediaFileUpload(str(image_path), mimetype="image/jpeg")).execute()
        print("[upload] Custom thumbnail set")
        return True
    except HttpError as exc:
        print(f"::warning::Thumbnail not set ({exc.resp.status}). Custom thumbnails need a phone-verified channel "
              "(youtube.com/verify); for Shorts YouTube may require Partner Program membership.")
        return False


def fetch_statistics(video_ids):
    """Returns {video_id: {"views": int, "likes": int, "comments": int}}; empty dict if not permitted."""
    stats = {}
    youtube = get_client()
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i + 50]
        try:
            resp = youtube.videos().list(part="statistics", id=",".join(batch), maxResults=50).execute()
        except HttpError as exc:
            if _permission_problem(exc):
                print("::warning::Statistics skipped - the refresh token lacks the 'youtube' permission (see README).")
            else:
                print(f"[stats] Could not load statistics: {exc}")
            return stats
        for item in resp.get("items", []):
            s = item.get("statistics", {})
            stats[item["id"]] = {
                "views": int(s.get("viewCount", 0)),
                "likes": int(s.get("likeCount", 0)),
                "comments": int(s.get("commentCount", 0)),
            }
    return stats
