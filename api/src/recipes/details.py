"""Work out each recipe's written recipe: its ingredients and method, and where
they're written.

Plain code settles the one case with a single answer: a video with one recipe and a
link to a page with recipe data. Claude decides the rest, from the video's links (and
the text of linked pages with no recipe data), description and creator comments. A
video with nothing to read is marked as looked at without asking.
"""

import re
from collections.abc import Sequence

from recipes.ai import AILine, DetailsAnswer, LinkText
from recipes.models import Details, Line, StoredPage, VideoToFill
from recipes.pages import NO_RECIPE, RECIPE

# What makes a video's text worth Claude reading: an ingredients heading (English,
# Swedish or German), or a few amounts. An amount starts a line, like "2 tomatoes"
# (but not a timestamp like "1:42 Breakfasts"), or has a unit, anywhere in a
# sentence, like "chop 100g of cherry tomatoes".
_INGREDIENTS_HEADING = re.compile(r"ingredien|zutaten", re.IGNORECASE)
_LINE_AMOUNT = re.compile(
    r"^\W*(?!\d{1,2}:\d{2})(?:\d|[½¼¾⅓⅔⅛]|a (?:pinch|handful))",
    re.IGNORECASE | re.MULTILINE,
)
_UNIT_AMOUNT = re.compile(
    r"(?:\d|[½¼¾⅓⅔⅛])\s*(?:g|kg|ml|l|dl|tbsp|tsp|cups?|oz|lbs?|tablespoons?"
    r"|teaspoons?)\b",
    re.IGNORECASE,
)
MIN_AMOUNTS = 3
_LINK = re.compile(r"https?://[^\s)]+")
# A bullet or emoji, a step's number like "1." or "2)", or a chapter's timestamp like
# "0:52", which Claude is told to leave out.
_LINE_START = re.compile(r"^\W*(?:\d{1,2}(?::\d{2}){1,2}\s*\W*|\d+[.)]\s+)?")
# What separates ingredients some creators write on one line: "{1x onion; 2x garlic}".
_ITEM_BREAK = re.compile(r"[;{}|]")


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
                        ingredients=[Line(text) for text in page.recipe.ingredients],
                        method=[Line(text) for text in page.recipe.method],
                    )
                }
    if not readable_pages(video) and not _worth_reading(video):
        return {recipe.id: Details(by="code") for recipe in video.recipes}
    return None


def readable_pages(video: VideoToFill) -> list[StoredPage]:
    """The pages Claude is shown: the ones that answered with a page."""
    return [page for page in video.pages if page.outcome in (RECIPE, NO_RECIPE)]


def links_for_claude(pages: Sequence[StoredPage]) -> list[LinkText]:
    return [
        LinkText(
            page.link_text,
            page.url,
            page.recipe.name if page.recipe else None,
            page.text,
        )
        for page in pages
    ]


def _worth_reading(video: VideoToFill) -> bool:
    """Whether the video's text may hold a recipe: ingredients, or chapters that may
    be its steps."""
    text = "\n".join([video.text.description, *video.text.creator_comments])
    return bool(
        len(video.text.chapters) >= MIN_AMOUNTS
        or _INGREDIENTS_HEADING.search(text)
        or len(_LINE_AMOUNT.findall(text)) >= MIN_AMOUNTS
        or len(_UNIT_AMOUNT.findall(text)) >= MIN_AMOUNTS
    )


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
                if page.recipe is not None:
                    ingredients = [Line(text) for text in page.recipe.ingredients]
                    method = [Line(text) for text in page.recipe.method]
                else:  # a place to look, unless Claude copied lines from its text
                    ingredients = copied_lines(item.ingredients, page.text or "")
                    method = copied_lines(item.method, page.text or "")
                found[recipe_id] = Details(
                    by="ai",
                    source="link",
                    source_url=page.url,
                    ingredients=ingredients or None,
                    method=method or None,
                    confidence=confidence,
                )
        elif item.source in ("description", "comment"):
            text = (
                video.text.description
                if item.source == "description"
                else "\n".join(video.text.creator_comments)
            )
            ingredients = copied_lines(item.ingredients, text)
            method = copied_lines(item.method, text)
            if ingredients or method:
                found[recipe_id] = Details(
                    by="ai",
                    source=item.source,
                    ingredients=ingredients or None,
                    method=method or None,
                    confidence=confidence,
                )
    return {id_: details for id_, details in found.items() if id_ in video.to_fill}


def copied_lines(lines: Sequence[AILine], text: str) -> list[Line]:
    """The lines that are whole lines of `text`, or items on one, ignoring case,
    spacing and any bullet or step number, so nothing Claude wrote or shortened
    itself is stored as the creator's recipe. Links in a line, often to a shop, are
    dropped."""
    lines_and_items = [
        part for line in text.splitlines() for part in [line, *_ITEM_BREAK.split(line)]
    ]
    written = {_squash(_LINE_START.sub("", part)) for part in lines_and_items}
    return [
        Line(_without_links(line.text), line.note)
        for line in lines
        if _without_links(line.text)
        and _squash(_LINE_START.sub("", line.text)) in written
    ]


def _without_links(line: str) -> str:
    line = _LINK.sub("", line)
    return re.sub(r"\(\s*\)", "", line).strip()  # and the brackets a link was in


def _squash(text: str) -> str:
    """`text` in lower case, with single spaces and straight quotes."""
    return " ".join(text.lower().translate(_STRAIGHT_QUOTES).split())


_STRAIGHT_QUOTES = str.maketrans("‘’“”", "''\"\"")
