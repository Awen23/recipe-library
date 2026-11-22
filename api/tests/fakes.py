"""A stand-in for the YouTube API, serving the saved responses in `fixtures/`."""

import json
from pathlib import Path
from typing import Any

import httpx2

FIXTURES = Path(__file__).parent / "fixtures"


def read_fixture(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class FakeYouTubeApi:
    """Answers requests the way the real API did, and records each request.

    `playlistItems` serves the real playlist in two pages: seven videos, including a
    deleted one (`Iop_LKTis_U`) and a private one (`d9yFMrsKQWk`). Page 1 ends with
    a `nextPageToken`; asking with any `pageToken` gets page 2, which has none.
    `videos` only has details for the videos in `videos.json`, so, like the real
    API, it leaves the deleted and private ones out.
    `commentThreads` serves the real top comments of `eG0tXlljTtI`, and none for
    any other video.
    """

    def __init__(self) -> None:
        self.requests: list[httpx2.Request] = []
        self.transport = httpx2.MockTransport(self._handle)

    def _handle(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        endpoint = request.url.path.rsplit("/", 1)[-1]
        if endpoint == "playlistItems":
            if request.url.params.get("pageToken"):
                page = read_fixture("playlist_items_page_2.json")
            else:
                page = read_fixture("playlist_items_page_1.json")
            return httpx2.Response(200, json=page)
        if endpoint == "videos":
            requested = request.url.params["id"].split(",")
            response = read_fixture("videos.json")
            response["items"] = [i for i in response["items"] if i["id"] in requested]
            return httpx2.Response(200, json=response)
        if endpoint == "commentThreads":
            if request.url.params["videoId"] == "eG0tXlljTtI":
                return httpx2.Response(200, json=read_fixture("comment_threads.json"))
            return httpx2.Response(200, json={"items": []})
        return httpx2.Response(404)
