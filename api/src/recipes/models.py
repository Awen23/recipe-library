"""The types the app passes between its parts. They hold no database or web code:
`storage` fills them from the database, and `details` and `building` work with them
to work out recipes.
"""

from dataclasses import dataclass
from typing import Literal

from recipes.ai import VideoText
from recipes.recipe_data import PageRecipe

# How interested I am in a recipe, as I rate it by hand.
Rating = Literal["would_cook", "curious", "not_for_me"]


@dataclass(frozen=True)
class Line:
    """One line of a written recipe: an ingredient or a step, or a note the creator
    wrote among them, like "*soaked overnight". Stored as JSON, as
    `{"text": ..., "note": ...}`, in the order written, so a note shows where it was
    written."""

    text: str
    note: bool = False


@dataclass(frozen=True)
class RecipeName:
    id: int
    name: str


@dataclass(frozen=True)
class StoredPage:
    """A fetched link, as working out details needs it."""

    url: str  # where it led, or as written when it didn't answer
    link_text: str
    outcome: str
    recipe: PageRecipe | None
    text: str | None  # the page's text, when it has no recipe data


@dataclass(frozen=True)
class VideoToFill:
    """A video with recipes whose details haven't been looked for, with what it
    holds."""

    id: str
    text: VideoText
    recipes: list[RecipeName]  # every recipe in the video, in order
    to_fill: set[int]  # the IDs of those whose details haven't been looked for
    pages: list[StoredPage]  # in the order the links are written


@dataclass(frozen=True)
class Details:
    """What looking for a recipe's written recipe found. All but `by` are None when
    nothing was found."""

    by: str  # who looked: "code" or "ai"
    source: str | None = None  # "link", "description" or "comment"
    source_url: str | None = None  # the page, when it's from a link
    ingredients: list[Line] | None = None  # None for a page that's a place to look
    method: list[Line] | None = None
    confidence: int | None = None  # 0-100, when AI decided
