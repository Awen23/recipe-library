"""Stand-ins for the YouTube API, the Claude API and the web, so tests never use the
network."""

import json
from pathlib import Path
from typing import Any

import httpx2

from recipes.ai import DETAILS_PROMPT, DetailsAnswer, VideoAnswer
from recipes.pages import Page, PageFetcher

FIXTURES = Path(__file__).parent / "fixtures"


def read_fixture(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def recorded_details(video_id: str) -> DetailsAnswer:
    """Claude's real details answer for a video, from `claude_details_replies.json`."""
    reply = read_fixture("claude_details_replies.json")[video_id]
    return DetailsAnswer.model_validate_json(reply["content"][0]["text"])


def read_page(name: str) -> str:
    """A page in `fixtures/pages/`, trimmed to its Recipe data."""
    return (FIXTURES / "pages" / name).read_text(encoding="utf-8")


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


class FakeClaudeApi:
    """A stand-in for the Claude Messages API, and records each request.

    It answers with Claude's real replies, picked by the title in the request: from
    `claude_replies.json` when asked for a video's recipes (all five videos in
    `videos.json`), and from `claude_details_replies.json` when asked for their
    details (the two videos plain code can't settle).
    Responses put in `queue` are served first, in order.
    """

    def __init__(self) -> None:
        self.requests: list[httpx2.Request] = []
        self.queue: list[httpx2.Response] = []
        self.transport = httpx2.MockTransport(self._handle)
        replies = read_fixture("claude_replies.json")
        details = read_fixture("claude_details_replies.json")
        videos = read_fixture("videos.json")["items"]
        self._replies = {v["snippet"]["title"]: replies[v["id"]] for v in videos}
        self._details = {
            v["snippet"]["title"]: details[v["id"]]
            for v in videos
            if v["id"] in details
        }

    def _handle(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        if self.queue:
            return self.queue.pop(0)
        body = json.loads(request.content)
        message = body["messages"][0]["content"]
        title = message.split("<title>", 1)[1].split("</title>", 1)[0]
        replies = self._details if body["system"] == DETAILS_PROMPT else self._replies
        return httpx2.Response(200, json=replies[title])


def recorded_answer(video_id: str) -> VideoAnswer:
    """Claude's real answer for a video in `videos.json`, from `claude_replies.json`."""
    reply = read_fixture("claude_replies.json")[video_id]
    return VideoAnswer.model_validate_json(reply["content"][0]["text"])


class FakeTime:
    """A clock that only moves when the code sleeps, recording each sleep."""

    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds

    def clock(self) -> float:
        return self.now


class FakeWeb:
    """Serves the responses in `pages`, by URL, and a 404 for any other URL,
    recording each request. A list of responses is served one per request."""

    def __init__(
        self, pages: dict[str, httpx2.Response | list[httpx2.Response]] | None = None
    ) -> None:
        self.pages = pages or {}
        self.requests: list[httpx2.Request] = []
        self.time = FakeTime()

    def _handle(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        page = self.pages.get(str(request.url), httpx2.Response(404))
        return page.pop(0) if isinstance(page, list) else page

    def fetcher(self) -> PageFetcher:
        """A PageFetcher that fetches from this fake, without waiting."""
        return PageFetcher(
            httpx2.MockTransport(self._handle),
            sleep=self.time.sleep,
            clock=self.time.clock,
        )

    def fetch(self, url: str) -> Page:
        return self.fetch_all([url])[0]

    def fetch_all(self, urls: list[str]) -> list[Page]:
        with self.fetcher() as fetcher:
            return [fetcher.fetch(url) for url in urls]
