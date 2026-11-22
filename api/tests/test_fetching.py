from dataclasses import replace

import httpx2
from sqlalchemy import Engine, select

from recipes.fetching import fetch_linked_pages
from recipes.playlist import fetch_playlist
from recipes.storage import recipe_links, save_playlist
from recipes.youtube import YouTubeClient

from fakes import FakeWeb, FakeYouTubeApi


def page_rows(engine: Engine) -> list[tuple[str, int, str, str, str]]:
    with engine.connect() as connection:
        query = select(
            recipe_links.c.video_id,
            recipe_links.c.position,
            recipe_links.c.url,
            recipe_links.c.link_text,
            recipe_links.c.outcome,
        ).order_by(recipe_links.c.video_id, recipe_links.c.position)
        return [tuple(row) for row in connection.execute(query)]  # type: ignore[misc]


def test_stores_what_each_link_led_to(fetched: Engine, fake_web: FakeWeb) -> None:
    with fake_web.fetcher() as fetcher:
        summary = fetch_linked_pages(fetched, fetcher)

    # The fake web has the three recipe pages, and every other link is a 404.
    # eG0tXlljTtI has no links.
    assert (summary.videos, summary.links, summary.recipes) == (4, 7, 3)
    assert page_rows(fetched)[:3] == [
        (
            "H0tkAEL6CS8",
            0,
            "https://www.theedgyveg.com/2023/04/24/3-ingredient-vegan-brownies/",
            "🌱 Brownie Recipes",
            "recipe",
        ),
        (
            "gOxwhuntyMY",
            0,
            "https://goodfoodbaddie.com/blueberry-baked-oatmeal/",
            "Full Recipe + Nutritional Info",
            "recipe",
        ),
        (
            "nHr9LqK3PKc",
            0,
            "https://bit.ly/3RflF7w",
            "✍Written Instructions on my Substack",
            "HTTP 404",
        ),
    ]


def test_each_fetch_fetches_only_the_new_videos_links(
    engine: Engine, fake_api: FakeYouTubeApi, fake_web: FakeWeb
) -> None:
    # `recipes fetch` runs whenever the playlist has new videos, and only works on
    # what's new. Here the oatmeal video is added to the playlist after a first fetch.
    with YouTubeClient("test-key", transport=fake_api.transport) as client:
        playlist = fetch_playlist(client, "PLAYLIST_ID")
    without_oatmeal = tuple(v for v in playlist.videos if v.id != "gOxwhuntyMY")
    save_playlist(replace(playlist, videos=without_oatmeal), engine)
    with fake_web.fetcher() as fetcher:
        fetch_linked_pages(engine, fetcher)
        before = len(fake_web.requests)
        save_playlist(playlist, engine)

        summary = fetch_linked_pages(engine, fetcher)

    assert (summary.videos, summary.links) == (1, 1)
    assert [str(r.url) for r in fake_web.requests[before:]] == [
        "https://goodfoodbaddie.com/blueberry-baked-oatmeal/"
    ]


def test_keeps_where_a_short_link_led(fetched: Engine) -> None:
    """Not from the data: the Substack page here is empty."""
    substack = "https://minarome.substack.com/"
    web = FakeWeb(
        {
            "https://bit.ly/3RflF7w": httpx2.Response(
                301, headers={"location": substack}
            ),
            substack: httpx2.Response(200, headers={"content-type": "text/html"}),
        }
    )

    with web.fetcher() as fetcher:
        fetch_linked_pages(fetched, fetcher)

    with fetched.connect() as connection:
        final_url, outcome = connection.execute(
            select(recipe_links.c.final_url, recipe_links.c.outcome).where(
                recipe_links.c.url == "https://bit.ly/3RflF7w"
            )
        ).one()
    assert (final_url, outcome) == (substack, "no recipe data")


def test_a_page_without_a_recipe_stores_null(
    fetched: Engine, fake_web: FakeWeb
) -> None:
    with fake_web.fetcher() as fetcher:
        fetch_linked_pages(fetched, fetcher)

    with fetched.connect() as connection:
        query = select(recipe_links.c.url).where(recipe_links.c.recipe.is_(None))
        assert len(connection.execute(query).all()) == 4  # SQL NULL, not "null"
