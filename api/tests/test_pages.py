"""The fetcher's rules, against a fake web. Apart from the first test, not from the
data: the sites here answer the way the HTTP rules say a site can, to test each
outcome."""

import httpx2

from recipes.pages import (
    BLOCKED,
    ERROR,
    MAX_BYTES,
    NO_RECIPE,
    NOT_A_PAGE,
    PRIVATE,
    RECIPE,
    RETRY_PAUSE_SECONDS,
    SAME_SITE_PAUSE_SECONDS,
    SKIPPED,
    TOO_BIG,
    USER_AGENT,
    Page,
    PageFetcher,
)

from fakes import FakeWeb, read_page

HTML = {"content-type": "text/html; charset=utf-8"}
NO_RECIPE_HTML = b"<html><body><p>Subscribe for recipes</p></body></html>"


def test_page_with_a_recipe() -> None:
    url = "https://goodfoodbaddie.com/blueberry-baked-oatmeal/"
    page = httpx2.Response(
        200, headers=HTML, text=read_page("blueberry_baked_oatmeal.html")
    )

    fetched = FakeWeb({url: page}).fetch(url)

    assert fetched.outcome == RECIPE
    assert fetched.recipe is not None
    assert fetched.recipe.name == "Blueberry Baked Oatmeal"


def test_page_without_recipe_data() -> None:
    web = FakeWeb(
        {"https://a.test/": httpx2.Response(200, headers=HTML, content=NO_RECIPE_HTML)}
    )

    assert web.fetch("https://a.test/") == Page(
        "https://a.test/", "https://a.test/", NO_RECIPE, None
    )
    assert web.requests[0].headers["user-agent"] == USER_AGENT


def test_follows_redirects_and_keeps_where_they_led() -> None:
    web = FakeWeb(
        {
            "https://short.test/abc": httpx2.Response(
                301, headers={"location": "https://blog.test/stew/"}
            ),
            "https://blog.test/stew/": httpx2.Response(
                200, headers=HTML, content=NO_RECIPE_HTML
            ),
        }
    )

    page = web.fetch("https://short.test/abc")

    assert (page.url, page.final_url) == (
        "https://short.test/abc",
        "https://blog.test/stew/",
    )


def test_does_not_fetch_a_skipped_site_a_link_redirects_to() -> None:
    web = FakeWeb(
        {
            "https://short.test/abc": httpx2.Response(
                302, headers={"location": "https://www.instagram.com/reel/abc/"}
            )
        }
    )

    assert web.fetch("https://short.test/abc").outcome == SKIPPED
    assert [str(r.url) for r in web.requests] == ["https://short.test/abc"]


def test_pauses_between_requests_to_the_same_site_only() -> None:
    web = FakeWeb(
        {
            url: httpx2.Response(200, headers=HTML, content=NO_RECIPE_HTML)
            for url in ("https://a.test/1", "https://a.test/2", "https://b.test/")
        }
    )

    web.fetch_all(["https://a.test/1", "https://b.test/", "https://a.test/2"])

    assert web.time.sleeps == [SAME_SITE_PAUSE_SECONDS]


def test_retries_once_when_a_site_is_busy() -> None:
    ok = httpx2.Response(200, headers=HTML, content=NO_RECIPE_HTML)
    web = FakeWeb({"https://a.test/": [httpx2.Response(429), ok]})

    assert web.fetch("https://a.test/").outcome == NO_RECIPE
    assert web.time.sleeps == [RETRY_PAUSE_SECONDS]


def test_gives_up_after_one_retry() -> None:
    web = FakeWeb({"https://a.test/": [httpx2.Response(503), httpx2.Response(503)]})

    assert web.fetch("https://a.test/").outcome == "HTTP 503"
    assert len(web.requests) == 2


def test_http_error() -> None:
    assert FakeWeb({}).fetch("https://a.test/gone").outcome == "HTTP 404"


def test_cloudflare_browser_check_is_blocked() -> None:
    web = FakeWeb(
        {"https://a.test/": httpx2.Response(403, headers={"cf-mitigated": "challenge"})}
    )

    assert web.fetch("https://a.test/").outcome == BLOCKED


def test_file_that_is_not_a_web_page() -> None:
    pdf = httpx2.Response(
        200, headers={"content-type": "application/pdf"}, content=b"%PDF"
    )

    assert (
        FakeWeb({"https://a.test/book.pdf": pdf})
        .fetch("https://a.test/book.pdf")
        .outcome
        == NOT_A_PAGE
    )


def test_stops_reading_a_page_over_the_size_limit() -> None:
    huge = httpx2.Response(200, headers=HTML, content=b"x" * (MAX_BYTES + 1))

    assert (
        FakeWeb({"https://a.test/": huge}).fetch("https://a.test/").outcome == TOO_BIG
    )


def test_no_response() -> None:
    def refuse(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("refused", request=request)

    with PageFetcher(httpx2.MockTransport(refuse), sleep=lambda _: None) as fetcher:
        assert fetcher.fetch("https://a.test/") == Page(
            "https://a.test/", None, ERROR, None
        )


def test_redirect_loop() -> None:
    loop = httpx2.Response(302, headers={"location": "https://a.test/"})

    assert FakeWeb({"https://a.test/": loop}).fetch("https://a.test/").outcome == ERROR


def test_a_charset_that_is_not_text_is_read_as_utf8() -> None:
    page = httpx2.Response(
        200, headers={"content-type": "text/html; charset=base64"}, content=b"<p>Hi"
    )

    assert FakeWeb({"https://a.test/": page}).fetch("https://a.test/").outcome == (
        NO_RECIPE
    )


def test_content_type_in_capitals() -> None:
    page = httpx2.Response(200, headers={"content-type": "Text/HTML"}, content=b"")

    assert FakeWeb({"https://a.test/": page}).fetch("https://a.test/").outcome == (
        NO_RECIPE
    )


def test_does_not_fetch_private_addresses() -> None:
    web = FakeWeb(
        {
            "https://short.test/abc": httpx2.Response(
                302, headers={"location": "http://192.168.1.1/admin"}
            )
        }
    )

    pages = web.fetch_all(["https://short.test/abc", "http://localhost:8000/"])

    assert [page.outcome for page in pages] == [PRIVATE, PRIVATE]
    assert [str(r.url) for r in web.requests] == ["https://short.test/abc"]
