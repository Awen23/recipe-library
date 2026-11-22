"""Fetch the pages that stored videos link to, and store what each holds.

A video's links are fetched once, the first time this runs after the video is stored.
"""

from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import Engine

from recipes import storage
from recipes.pages import RECIPE, Page, PageFetcher


@dataclass
class FetchSummary:
    """What fetching pages did."""

    videos: int = 0
    links: int = 0
    recipes: int = 0  # links that led to a page with a recipe


def fetch_linked_pages(
    engine: Engine,
    fetcher: PageFetcher,
    on_video: Callable[[str, list[Page]], None] | None = None,
) -> FetchSummary:
    """Fetch the links of each video whose links haven't been fetched, storing each
    video's pages as soon as they're fetched, so a fetch that stops part way keeps
    what it did. `on_video` is told about each video when it's done."""
    summary = FetchSummary()
    for video_id, links in storage.videos_to_fetch_pages(engine):
        pages = [fetcher.fetch(link.url) for link in links]
        storage.save_pages(engine, video_id, list(zip(links, pages, strict=True)))
        summary.videos += 1
        summary.links += len(pages)
        summary.recipes += sum(page.outcome == RECIPE for page in pages)
        if on_video is not None:
            on_video(video_id, pages)
    return summary
