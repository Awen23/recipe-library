"""Fetch the web pages that videos link to, politely, and read their recipes."""

import ipaddress
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Self

import httpx2

from recipes.links import is_skipped
from recipes.recipe_data import NoRecipeError, PageRecipe, read_recipe

# Names the app and nothing about whoever runs it.
USER_AGENT = "recipe-library/0.1 (a personal recipe index)"
TIMEOUT_SECONDS = 20
MAX_BYTES = 5_000_000  # recipe pages are well under this
MAX_REDIRECTS = 10
SAME_SITE_PAUSE_SECONDS = 1.5  # between two requests to the same site
RETRY_PAUSE_SECONDS = 10  # before the one retry after a 429 or 503
_RETRY_STATUSES = (429, 503)  # too many requests, or busy: worth one more try

# How fetching a link went. An HTTP error is stored as `HTTP <status>`.
RECIPE = "recipe"
NO_RECIPE = "no recipe data"
SKIPPED = "skipped"  # it redirected to a skipped site, which isn't fetched
BLOCKED = "blocked"  # the site asked for a browser check, which isn't attempted
NOT_A_PAGE = "not a web page"  # a PDF, image or other file
TOO_BIG = "too big"
PRIVATE = "private address"  # this computer or its network, which isn't fetched
ERROR = "error"  # no response: a timeout, a bad address, too many redirects


@dataclass(frozen=True)
class Page:
    """What came of fetching one link."""

    url: str  # as written in the video
    final_url: str | None  # where it led after redirects, if it got a response
    outcome: str
    recipe: PageRecipe | None  # when the outcome is RECIPE


class PageFetcher:
    """Fetches one page at a time, pausing between requests to the same site.

    `sleep` and `clock` are for tests, which pass fakes to avoid waiting.
    """

    def __init__(
        self,
        transport: httpx2.BaseTransport | None = None,
        *,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._client = httpx2.Client(
            transport=transport,
            headers={"User-Agent": USER_AGENT},
            timeout=TIMEOUT_SECONDS,
        )
        self._sleep = sleep
        self._clock = clock
        self._last_request: dict[str, float] = {}  # by host

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self._client.close()

    def fetch(self, url: str) -> Page:
        """Fetch `url`, following its redirects, and read the recipe it holds."""
        try:
            request = self._client.build_request("GET", url)
        except httpx2.InvalidURL:
            return Page(url, None, ERROR, None)
        retried = False
        for _ in range(MAX_REDIRECTS + 1):
            # Checked at every step, so a short link to a skipped site isn't fetched
            # past the redirect.
            if is_skipped(str(request.url)):
                return Page(url, str(request.url), SKIPPED, None)
            if _is_private(request.url.host):
                return Page(url, str(request.url), PRIVATE, None)
            try:
                response = self._send(request)
            except httpx2.HTTPError:
                return Page(url, None, ERROR, None)
            try:
                if response.next_request is not None:  # a redirect
                    request = response.next_request
                    continue
                if response.status_code in _RETRY_STATUSES and not retried:
                    retried = True
                    self._sleep(RETRY_PAUSE_SECONDS)
                    continue
                return self._read(url, response)
            finally:
                response.close()
        return Page(url, None, ERROR, None)

    def _send(self, request: httpx2.Request) -> httpx2.Response:
        host = request.url.host
        if host in self._last_request:
            wait = SAME_SITE_PAUSE_SECONDS - (self._clock() - self._last_request[host])
            if wait > 0:
                self._sleep(wait)
        try:
            return self._client.send(request, stream=True)
        finally:
            self._last_request[host] = self._clock()

    def _read(self, url: str, response: httpx2.Response) -> Page:
        final_url = str(response.url)
        # How Cloudflare marks a browser check: https://developers.cloudflare.com/cloudflare-challenges/challenge-types/challenge-pages/detect-response/
        if response.headers.get("cf-mitigated") == "challenge":
            return Page(url, final_url, BLOCKED, None)
        if response.status_code >= 400:
            return Page(url, final_url, f"HTTP {response.status_code}", None)
        if "html" not in response.headers.get("content-type", "text/html").lower():
            return Page(url, final_url, NOT_A_PAGE, None)
        try:
            body = bytearray()
            for chunk in response.iter_bytes():
                body += chunk
                if len(body) > MAX_BYTES:
                    return Page(url, final_url, TOO_BIG, None)
        except httpx2.HTTPError:
            return Page(url, final_url, ERROR, None)
        try:
            html = body.decode(response.encoding or "utf-8", errors="replace")
        except LookupError:  # a charset Python knows that isn't text, like "base64"
            html = body.decode("utf-8", errors="replace")
        try:
            recipe = read_recipe(html, final_url)
        except NoRecipeError:
            return Page(url, final_url, NO_RECIPE, None)
        return Page(url, final_url, RECIPE, recipe)


def _is_private(host: str) -> bool:
    """Whether `host` is this computer, or an IP address on a private network.
    Links are untrusted, so one mustn't reach something only this computer can."""
    if host == "localhost" or host.endswith(".localhost"):
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:  # a hostname
        return False
    return not address.is_global
