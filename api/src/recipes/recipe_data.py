"""Read a written recipe from a web page's schema.org Recipe data, using
recipe-scrapers: https://docs.recipe-scrapers.com/

Pages are untrusted. recipe-scrapers only parses them: it unescapes HTML entities
and drops leftover tags, and nothing from a page is run.
"""

from dataclasses import dataclass
from typing import Any

from recipe_scrapers import scrape_html


@dataclass(frozen=True)
class PageRecipe:
    """A recipe as a web page describes it."""

    name: str
    ingredients: list[str]  # one line each, as written, such as "1 cup oats"
    method: list[str]  # the steps, in order


class NoRecipeError(Exception):
    """The page has no Recipe data that recipe-scrapers can read."""


def read_recipe(html: str, url: str) -> PageRecipe:
    """The first recipe in a page's Recipe data. `url` is where the page was fetched
    from, after redirects, which picks a site-specific reader when there is one.

    Raises NoRecipeError when there's no recipe with ingredients.
    """
    try:
        scraper = scrape_html(html, url, supported_only=False)
        recipe = PageRecipe(
            name=scraper.title(),
            ingredients=scraper.ingredients(),
            method=_method(scraper),
        )
    # recipe-scrapers raises its own errors for a missing field, and a site-specific
    # reader can fail in its own way on a page it doesn't expect. Either way the page
    # is someone else's, so it's a page we can't read, not a bug here.
    except Exception as error:
        raise NoRecipeError(f"{type(error).__name__}: {error}") from error
    if not recipe.ingredients:
        raise NoRecipeError("no ingredients")
    return recipe


def _method(scraper: Any) -> list[str]:
    """The steps, or none when the page only lists ingredients."""
    try:
        return list(scraper.instructions_list())
    except Exception:  # for the same reason as in read_recipe
        return []
