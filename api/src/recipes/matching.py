"""Work out which of a video's fetched pages holds which of its recipes.

Plain code, comparing names: a page's recipe name, and the words written beside its
link, against the recipe names in the video.
"""

import re
import unicodedata
from difflib import SequenceMatcher

from recipes.pages import NO_RECIPE, RECIPE
from recipes.storage import Details, StoredPage, VideoToFill

# How alike two names must be, 0-100, for a page to be matched to a recipe.
MIN_SCORE = 60
_WORD_ALIKE = 0.8  # how alike two words must be to count as the same, 0-1

# Words that say nothing about which dish it is.
_FILLER = {"a", "and", "for", "my", "of", "recipe", "the", "vegan", "w", "with"}
# Words beside a link that say it leads to a written recipe.
_POINTS_TO_RECIPE = re.compile(r"recipe|instruction|ingredient", re.IGNORECASE)


def match_video(video: VideoToFill) -> dict[int, Details]:
    """The details found for each of the video's recipes that has none, by ID."""
    if len(video.recipes) == 1:
        found = _match_only_recipe(video.recipes[0].id, video.pages)
    else:
        found = _match_by_name(video)
    return {id_: details for id_, details in found.items() if id_ in video.to_fill}


def _match_only_recipe(recipe_id: int, pages: list[StoredPage]) -> dict[int, Details]:
    """A video with one recipe takes the first page with a recipe. Failing that, the
    first readable page whose link says it's the recipe, as a place to look."""
    for page in pages:
        if page.recipe is not None:
            return {recipe_id: _from_recipe(page, None)}
    for page in pages:
        if page.outcome == NO_RECIPE and _POINTS_TO_RECIPE.search(page.link_text):
            return {recipe_id: Details(page.url, None, None, None)}
    return {}


def _match_by_name(video: VideoToFill) -> dict[int, Details]:
    """Pair recipes with pages, best-scoring pairs first, each page used once."""
    pairs = []
    for recipe in video.recipes:
        for position, page in enumerate(video.pages):
            if page.outcome not in (RECIPE, NO_RECIPE):
                continue
            names = [page.link_text]
            if page.recipe is not None:
                names.append(page.recipe.name)
            score = max(similarity(recipe.name, name) for name in names)
            if score >= MIN_SCORE:
                # A page with a recipe beats one that's only a place to look.
                pairs.append((score, page.recipe is not None, recipe.id, position))

    found: dict[int, Details] = {}
    used: set[int] = set()
    for score, _, recipe_id, position in sorted(pairs, reverse=True):
        if recipe_id in found or position in used:
            continue
        page = video.pages[position]
        found[recipe_id] = (
            _from_recipe(page, score)
            if page.recipe is not None
            else Details(page.url, None, None, score)
        )
        used.add(position)
    return found


def _from_recipe(page: StoredPage, score: int | None) -> Details:
    assert page.recipe is not None
    return Details(page.url, page.recipe.ingredients, page.recipe.method, score)


def similarity(name: str, text: str) -> int:
    """How much of recipe `name` is in `text`, 0-100: the share of its words found
    there, or how alike the two are written as one word ("Kebab pizza" and
    "kebabpizza")."""
    name_words, text_words = _words(name), _words(text)
    if not name_words or not text_words:
        return 0
    found = sum(any(_alike(word, other) for other in text_words) for word in name_words)
    joined = _alike("".join(name_words), "".join(text_words))
    return 100 if joined else round(100 * found / len(name_words))


def _words(text: str) -> list[str]:
    # "Grão" and "grao" are the same word, and so are "&", "+" and "and".
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    # Drop asides such as "(4)" for servings, and "@someone" for who inspired it.
    text = re.sub(r"\([^)]*\)|@\S+", " ", text)
    return [w for w in re.findall(r"[a-z0-9]+", text) if w not in _FILLER]


def _alike(a: str, b: str) -> bool:
    return SequenceMatcher(None, a, b).ratio() >= _WORD_ALIKE
