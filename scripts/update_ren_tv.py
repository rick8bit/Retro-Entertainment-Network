
import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

API_KEY = os.environ.get("YOUTUBE_API_KEY", "").strip()
DATA_FILE = Path("ren-tv.json")
BASE_URL = "https://www.googleapis.com/youtube/v3/"

CHANNELS = [
    "rick8bit",
    "4sidesofthering",
    "altfbpanel",
    "vikingwaxpress",
]


def youtube_request(endpoint, **params):
    params["key"] = API_KEY
    url = BASE_URL + endpoint + "?" + urllib.parse.urlencode(params)

    request = urllib.request.Request(
        url,
        headers={"User-Agent": "REN-TV/1.0"}
    )

    with urllib.request.urlopen(request, timeout=25) as response:
        return json.load(response)


def get_channel(handle):
    result = youtube_request(
        "channels",
        part="id,contentDetails",
        forHandle=handle
    )

    items = result.get("items", [])

    if not items:
        raise ValueError(f"Channel not found: {handle}")

    return items[0]


def get_latest_upload(uploads_playlist):
    result = youtube_request(
        "playlistItems",
        part="snippet",
        playlistId=uploads_playlist,
        maxResults=10
    )

    items = result.get("items", [])

    for item in items:
        snippet = item.get("snippet", {})
        video_id = snippet.get("resourceId", {}).get("videoId")
        title = snippet.get("title", "")

        if video_id and title not in (
            "Private video",
            "Deleted video"
        ):
            return {
                "video": video_id,
                "title": title,
                "isLive": False
            }

    return None


def get_current_live(channel_id):
    result = youtube_request(
        "search",
        part="snippet",
        channelId=channel_id,
        eventType="live",
        type="video",
        maxResults=5
    )

    for item in result.get("items", []):
        video_id = item.get("id", {}).get("videoId")

        if video_id:
            return {
                "video": video_id,
                "title": item.get("snippet", {}).get("title", ""),
                "isLive": True
            }

    return None


def main():
    if not API_KEY:
        raise RuntimeError(
            "Missing YOUTUBE_API_KEY GitHub Actions secret."
        )

    if DATA_FILE.exists():
        data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    else:
        data = {"channels": []}

    previous = {
        channel["handle"]: channel
        for channel in data.get("channels", [])
        if "handle" in channel
    }

    updated = []

    # Search for live broadcasts every 6 hours.
    # Latest uploads are checked every workflow run.
    now = datetime.now(timezone.utc)
    check_live = now.hour % 6 == 0 and now.minute < 30

    for handle in CHANNELS:
        old = previous.get(handle, {
            "handle": handle,
            "video": "",
            "title": "",
            "isLive": False
        })

        try:
            channel = get_channel(handle)
            channel_id = channel["id"]

            playlist = channel["contentDetails"][
                "relatedPlaylists"
            ]["uploads"]

            latest = get_latest_upload(playlist)

            live = None

            if check_live:
                live = get_current_live(channel_id)

            # Preserve a known live broadcast between checks,
            # until the next live check or an updated selection.
            if live:
                selection = live
            elif check_live:
                selection = latest or old
            elif old.get("isLive"):
                selection = old
            else:
                selection = latest or old

            updated.append({
                "handle": handle,
                "video": selection.get("video", ""),
                "title": selection.get("title", ""),
                "isLive": selection.get("isLive", False)
            })

            print(f"{handle}: {selection.get('title', 'No video')}")

        except Exception as error:
            print(f"Could not update {handle}: {error}")
            updated.append(old)

    data["updatedAt"] = now.isoformat()
    data["channels"] = updated

    DATA_FILE.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8"
    )

    print("REN TV programming updated.")


if __name__ == "__main__":
    main()
