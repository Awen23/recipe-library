"""Work out each recipe's written recipe: its ingredients and method, and where
they're written.

Plain code settles the one case with a single answer: a video with one recipe and a
link to a page with recipe data. Claude decides the rest, from the video's links,
description and creator comments. A video with nothing to read is marked as looked
at without asking.
"""

import re
from collections.abc import Sequence

from recipes.ai import DetailsAnswer, LinkText
from recipes.pages import NO_RECIPE, RECIPE
from recipes.storage import Details, StoredPage, VideoToFill

# A line that starts with an amount, like "2 tbsp soy sauce" or "½ cup oats", or an
# "Ingredients" heading. A video needs a few before its text is worth reading.
_INGREDIENT_LINE = re.compile(
    r"^\W*(?:\d|[½¼¾⅓⅔⅛]|a (?:pinch|handful)|ingredients)", re.IGNORECASE | re.MULTILINE
)
MIN_INGREDIENT_LINES = 3


def plain_details(video: VideoToFill) -> dict[int, Details] | None:
    """The details plain code can settle, by recipe ID, or None when Claude is
    needed."""
    if len(video.recipes) == 1:
        for page in video.pages:
            if page.recipe is not None:
                return {
                    video.recipes[0].id: Details(
                        by="code",
                        source="link",
                        source_url=page.url,
                        ingredients=page.recipe.ingredients,
                        method=page.recipe.method,
                    )
                }
    if not readable_pages(video) and not _has_ingredient_lines(video):
        return {recipe.id: Details(by="code") for recipe in video.recipes}
    return None


def readable_pages(video: VideoToFill) -> list[StoredPage]:
    """The pages Claude is shown: the ones that answered with a page."""
    return [page for page in video.pages if page.outcome in (RECIPE, NO_RECIPE)]


def links_for_claude(pages: Sequence[StoredPage]) -> list[LinkText]:
    return [
        LinkText(page.link_text, page.url, page.recipe.name if page.recipe else None)
        for page in pages
    ]


def _has_ingredient_lines(video: VideoToFill) -> bool:
    text = "\n".join([video.text.description, *video.text.creator_comments])
    return len(_INGREDIENT_LINE.findall(text)) >= MIN_INGREDIENT_LINES


def from_answer(
    video: VideoToFill, pages: Sequence[StoredPage], answer: DetailsAnswer | None
) -> dict[int, Details]:
    """The details Claude found for each recipe, by ID. `pages` are the pages it was
    shown, in order. A recipe Claude gave no usable answer for is marked as looked
    at, with nothing found, so it isn't asked about again."""
    found = {recipe.id: Details(by="ai") for recipe in video.recipes}
    for item in answer.recipes if answer else []:
        if not 0 <= item.recipe < len(video.recipes):
            continue
        recipe_id = video.recipes[item.recipe].id
        confidence = min(max(item.confidence, 0), 100)
        if item.source == "link" and item.link is not None:
            if 0 <= item.link < len(pages):
                page = pages[item.link]
                found[recipe_id] = Details(
                    by="ai",
                    source="link",
                    source_url=page.url,
                    ingredients=page.recipe.ingredients if page.recipe else None,
                    method=page.recipe.method if page.recipe else None,
                    confidence=confidence,
                )
        elif item.source in ("description", "comment"):
            text = (
                video.text.description
                if item.source == "description"
                else "\n".join(video.text.creator_comments)
            )
            ingredients = copied_lines(item.ingredients, text)
            if ingredients:
                found[recipe_id] = Details(
                    by="ai",
                    source=item.source,
                    ingredients=ingredients,
                    method=copied_lines(item.method, text),
                    confidence=confidence,
                )
    return {id_: details for id_, details in found.items() if id_ in video.to_fill}


def copied_lines(lines: Sequence[str], text: str) -> list[str]:
    """The lines that really are in `text`, ignoring case and spacing, so nothing
    Claude wrote itself is stored as the creator's recipe."""
    written = _squash(text)
    return [line.strip() for line in lines if line.strip() and _squash(line) in written]


def _squash(text: str) -> str:
    return " ".join(text.lower().split())
