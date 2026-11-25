"""Uploads the finished Short through the official YouTube Data API."""

import os
import time

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from . import channel_config as cfg

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def _client():
    missing = [k for k in ("YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN") if not os.environ.get(k)]
    if missing:
        raise RuntimeError(f"Missing GitHub secrets: {', '.join(missing)}")
    creds = Credentials(
        None,
        refresh_token=os.environ["YT_REFRESH_TOKEN"].strip(),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.environ["YT_CLIENT_ID"].strip(),
        client_secret=os.environ["YT_CLIENT_SECRET"].strip(),
        scopes=SCOPES,
    )
    creds.refresh(Request())
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def upload(video_path, title, description, tags):
    youtube = _client()
    body = {
        "snippet": {
            "title": title,
            "description": description[:4900],
            "tags": tags,
            "categoryId": cfg.YOUTUBE_CATEGORY_ID,
            "defaultLanguage": "en",
            "defaultAudioLanguage": "en",
        },
        "status": {
            "privacyStatus": cfg.PRIVACY_STATUS,
            "selfDeclaredMadeForKids": False,
            "containsSyntheticMedia": cfg.DECLARE_SYNTHETIC_MEDIA,
        },
    }
    media = MediaFileUpload(str(video_path), mimetype="video/mp4", chunksize=8 * 1024 * 1024, resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response, retries = None, 0
    while response is None:
        try:
            _, response = request.next_chunk()
        except HttpError as exc:
            if exc.resp.status in (500, 502, 503, 504) and retries < 5:
                retries += 1
                time.sleep(10 * retries)
                continue
            raise
    video_id = response["id"]
    status = response.get("status", {}).get("privacyStatus")
    print(f"[upload] Uploaded https://youtube.com/shorts/{video_id} (status: {status})")
    if cfg.PRIVACY_STATUS == "public" and status != "public":
        print("::warning::YouTube set the video to private. The Google Cloud project probably needs the "
              "free YouTube API audit (see README, section 'Videos bleiben privat').")
    return video_id, status
