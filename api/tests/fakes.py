"""A stand-in for the YouTube API, serving the saved responses in `fixtures/`."""

import json
from pathlib import Path
from typing import Any

import httpx

FIXTURES = Path(__file__).parent / "fixtures"


def read_fixture(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class FakeYouTubeApi:
    """Answers requests the way the real API did, and records each request.

    `playlistItems` serves the first page of the real playlist, which still lists a
    deleted video (`Iop_LKTis_U`).
    """

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.transport = httpx.MockTransport(self._handle)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        endpoint = request.url.path.rsplit("/", 1)[-1]
        if endpoint == "playlistItems":
            return httpx.Response(200, json=read_fixture("playlist_items_page_1.json"))
        return httpx.Response(404)
