import httpx2
from sqlalchemy import Engine, select

from recipes.fetching import fetch_linked_pages
from recipes.storage import video_links

from fakes import FakeWeb


def page_rows(engine: Engine) -> list[tuple[str, int, str, str, str]]:
    with engine.connect() as connection:
        query = select(
            video_links.c.video_id,
            video_links.c.position,
            video_links.c.url,
            video_links.c.link_text,
            video_links.c.outcome,
        ).order_by(video_links.c.video_id, video_links.c.position)
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


def test_links_already_fetched_are_not_fetched_again(
    fetched: Engine, fake_web: FakeWeb
) -> None:
    # `recipes fetch` runs whenever the playlist has new videos. Only their links
    # are fetched: the stored videos' links were fetched the first time.
    with fake_web.fetcher() as fetcher:
        fetch_linked_pages(fetched, fetcher)
        before = len(fake_web.requests)

        assert fetch_linked_pages(fetched, fetcher).links == 0
    assert len(fake_web.requests) == before


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
            select(video_links.c.final_url, video_links.c.outcome).where(
                video_links.c.url == "https://bit.ly/3RflF7w"
            )
        ).one()
    assert (final_url, outcome) == (substack, "no recipe data")


def test_a_page_without_a_recipe_stores_null(
    fetched: Engine, fake_web: FakeWeb
) -> None:
    with fake_web.fetcher() as fetcher:
        fetch_linked_pages(fetched, fetcher)

    with fetched.connect() as connection:
        query = select(video_links.c.url).where(video_links.c.recipe.is_(None))
        assert len(connection.execute(query).all()) == 4  # SQL NULL, not "null"
