import pytest

from recipes.matching import MIN_SCORE, match_video, similarity
from recipes.pages import NO_RECIPE, RECIPE
from recipes.recipe_data import PageRecipe
from recipes.storage import Details, RecipeName, StoredPage, VideoToFill


@pytest.mark.parametrize(
    ("name", "text"),
    [
        # Recipe names from the playlist, and the words beside their links.
        ("Marry me chickpeas", "Marry Me Chickpeas"),
        ("Chickpea and broccoli burritos", "Chickpea + Broccoli Burritos"),
        ("Salada de grão de bico", "Salada de Grão de Bico"),
        ("Kebab pizza", "kebabpizza"),
        ("High protein bagels", "High protein bagel |  (2; made double batch)"),
        (
            "Crispy tofu and potato sando",
            "crispy tofu & potato sando, inspired by @rhi.scran ()",
        ),
        ("Vegan fried egg", "⇨FULL RECIPE for Vegan Fried Egg"),
    ],
)
def test_names_that_match(name: str, text: str) -> None:
    assert similarity(name, text) >= MIN_SCORE


@pytest.mark.parametrize(
    ("name", "text"),
    [
        # From the same videos, a link beside another dish, or beside no dish.
        ("Buffalo chickpea wrap", "Recipe for homemade buffalo sauce"),
        ("Vegan omelette", "Recipe from"),
        ("Fava wraps", "✍Subscribe to my Substack"),
    ],
)
def test_names_that_do_not_match(name: str, text: str) -> None:
    assert similarity(name, text) < MIN_SCORE


# Three of the recipes in IMs-LLKFHao, and three of its links.
LENTIL_RECIPES = [
    RecipeName(1, "Lentil sloppy joes"),
    RecipeName(2, "Harissa red lentil meatballs"),
    RecipeName(3, "Gochujang glazed red lentil tofu"),
]
LENTIL_PAGES = [
    StoredPage(
        "https://www.spendwithpennies.com/lentil-sloppy-joes/",
        "lentil sloppy joes",
        NO_RECIPE,
        None,
    ),
    StoredPage(
        "https://www.wearesovegan.com/harissa-lentil-meatball-bowl/",
        "harissa red lentil meatballs",
        NO_RECIPE,
        None,
    ),
    StoredPage(
        "https://www.daringgourmet.com/misir-wat-ethiopian-spiced-red-lentils/",
        "misir wot",
        NO_RECIPE,
        None,
    ),
]


def test_each_recipe_gets_the_page_beside_its_name() -> None:
    video = VideoToFill("IMs-LLKFHao", LENTIL_RECIPES, {1, 2, 3}, LENTIL_PAGES)

    assert match_video(video) == {
        1: Details(LENTIL_PAGES[0].url, None, None, 100),
        2: Details(LENTIL_PAGES[1].url, None, None, 100),
        # The tofu has no link of its own.
    }


def test_only_recipes_without_details_are_filled() -> None:
    video = VideoToFill("IMs-LLKFHao", LENTIL_RECIPES, {2}, LENTIL_PAGES)

    assert list(match_video(video)) == [2]


def test_pages_that_did_not_answer_are_not_matched() -> None:
    gone = [StoredPage(p.url, p.link_text, "HTTP 404", None) for p in LENTIL_PAGES]

    assert (
        match_video(VideoToFill("IMs-LLKFHao", LENTIL_RECIPES, {1, 2, 3}, gone)) == {}
    )


def test_a_page_is_given_to_one_recipe() -> None:
    # Not from the data: one link beside two recipe names, as in "masala potatoes +
    # red lentil pancakes". It goes to the one whose name is the closer fit.
    recipes = [RecipeName(1, "Red lentil pancakes"), RecipeName(2, "Lentil pancakes")]
    page = StoredPage("https://a.test/", "Lentil pancakes", NO_RECIPE, None)

    assert list(match_video(VideoToFill("v", recipes, {1, 2}, [page]))) == [2]


def test_a_page_with_a_recipe_beats_a_place_to_look() -> None:
    # Not from the data: two links beside the same name, one with Recipe data.
    recipes = [RecipeName(1, "Misir wot"), RecipeName(2, "Shiro wot")]
    recipe = PageRecipe("Misir wot", ["1 cup red lentils"], ["Simmer."])
    pages = [
        StoredPage("https://a.test/", "misir wot", NO_RECIPE, None),
        StoredPage("https://b.test/", "misir wot", RECIPE, recipe),
    ]

    assert match_video(VideoToFill("v", recipes, {1, 2}, pages)) == {
        1: Details("https://b.test/", ["1 cup red lentils"], ["Simmer."], 100)
    }


ONE_RECIPE = [RecipeName(1, "Blueberry baked oatmeal")]


def test_one_recipe_video_takes_the_first_page_with_a_recipe() -> None:
    # Not from the data: the rule that names aren't compared when there's only one
    # recipe, so the page's own name can differ.
    recipe = PageRecipe("Baked Oats", ["1 cup oats"], [])
    pages = [
        StoredPage("https://a.test/", "My website", NO_RECIPE, None),
        StoredPage("https://b.test/", "Full Recipe", RECIPE, recipe),
    ]

    assert match_video(VideoToFill("v", ONE_RECIPE, {1}, pages)) == {
        1: Details("https://b.test/", ["1 cup oats"], [], None)
    }


@pytest.mark.parametrize(
    ("link_text", "matched"),
    [
        # From the playlist: links on Substack, which has no Recipe data.
        ("✍Written Instructions on my Substack", True),
        ("✍Subscribe to my Substack", False),
    ],
)
def test_one_recipe_video_without_recipe_data_takes_a_link_that_says_recipe(
    link_text: str, matched: bool
) -> None:
    page = StoredPage("https://minarome.substack.com/", link_text, NO_RECIPE, None)

    found = match_video(VideoToFill("v", ONE_RECIPE, {1}, [page]))

    assert found == ({1: Details(page.url, None, None, None)} if matched else {})
