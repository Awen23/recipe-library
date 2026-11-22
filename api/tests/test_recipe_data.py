import pytest

from recipes.recipe_data import NoRecipeError, PageRecipe, read_recipe

from fakes import read_page

OATMEAL_URL = "https://goodfoodbaddie.com/blueberry-baked-oatmeal/"
STEW_URL = "https://makeitdairyfree.com/one-pot-west-african-peanut-stew-vegan/"
BROWNIES_URL = "https://www.theedgyveg.com/2023/04/24/3-ingredient-vegan-brownies/"


def test_reads_json_ld() -> None:
    recipe = read_recipe(read_page("blueberry_baked_oatmeal.html"), OATMEAL_URL)

    assert recipe.name == "Blueberry Baked Oatmeal"
    assert len(recipe.ingredients) == 11
    assert recipe.ingredients[0] == (
        "2 1/2 cups Rolled Oats (ensure gluten-free if necessary)"
    )
    assert recipe.method[0] == "Preheat the oven to 375°F."


def test_reads_microdata() -> None:
    recipe = read_recipe(read_page("vegan_brownies.html"), BROWNIES_URL)

    assert recipe == PageRecipe(
        name="3-Ingredient Vegan Brownies",
        ingredients=[
            "¾ cup brewed coffee",
            "1-15 oz can of black beans, drained & rinsed (keep the aquafaba for "
            "baking!)",
            "1 package brownie mix",
            "1 cup chocolate chips, divided (optional)",
        ],
        method=recipe.method,
    )
    assert len(recipe.method) == 8


def test_reads_a_page_whose_name_differs_from_the_video() -> None:
    recipe = read_recipe(read_page("west_african_peanut_stew.html"), STEW_URL)

    assert recipe.name == "West African Peanut Stew (One Pot Vegan Recipe)"
    assert (len(recipe.ingredients), len(recipe.method)) == (24, 5)


def test_a_page_without_recipe_data() -> None:
    # Not from the data: a page with no Recipe, like a blog's home page.
    with pytest.raises(NoRecipeError):
        read_recipe("<html><body><h1>Welcome!</h1></body></html>", OATMEAL_URL)


def test_a_recipe_without_ingredients_is_no_recipe() -> None:
    # Not from the data: Recipe data that only names the dish.
    page = (
        '<script type="application/ld+json">'
        '{"@context": "https://schema.org", "@type": "Recipe", "name": "Stew"}'
        "</script>"
    )

    with pytest.raises(NoRecipeError):
        read_recipe(page, STEW_URL)
