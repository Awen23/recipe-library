import pytest

from recipes.links import Link, find_links, is_skipped

from fakes import read_fixture

DESCRIPTIONS = read_fixture("descriptions.json")


def test_keeps_recipe_links_with_the_words_on_their_line() -> None:
    links = find_links(DESCRIPTIONS["nHr9LqK3PKc"], [])

    # Squarespace, Vinted, YouTube, Amazon, Spotify and SoundCloud are skipped.
    assert links == [
        Link("https://bit.ly/3RflF7w", "✍Written Instructions on my Substack"),
        Link(
            "https://makeitdairyfree.com/one-pot-west-african-peanut-stew-vegan/",
            "West African Stew",
        ),
    ]


def test_skips_social_media_and_shopping_links() -> None:
    links = find_links(DESCRIPTIONS["whr7iOKRXTA"], [])

    # Instagram, Amazon and ShopMy links are skipped. Shops that aren't on the list,
    # like the chopping board's, are kept: fetching them finds no recipe.
    assert [link.url for link in links] == [
        "https://www.amandaducks.com/",
        "https://pinchyproducts.com.au/products/scallopini-chopping-board",
        "https://santokuknives.co.uk?dt_id=525045",
    ]


def test_link_alone_on_its_line_takes_the_line_before() -> None:
    # The creator's comment on W9jQkOyjmAs.
    comment = (
        "🖨️Written Recipe Here⬇️⬇️ \n"
        "https://fullkitchenrecipes.com/easy-chana-masala-chickpea-curry"
    )

    assert find_links("", [comment]) == [
        Link(
            "https://fullkitchenrecipes.com/easy-chana-masala-chickpea-curry",
            "🖨️Written Recipe Here⬇️⬇️",
        )
    ]


def test_description_links_come_before_comment_links_without_repeats() -> None:
    # Not from the data: the rule that each link is kept once, where it first appears.
    description = "Recipe: https://plantyou.com/vegan-taquitos/"
    comment = "Full recipe here https://plantyou.com/vegan-taquitos/"

    assert find_links(description, [comment]) == [
        Link("https://plantyou.com/vegan-taquitos/", "Recipe")
    ]


def test_drops_punctuation_after_a_link() -> None:
    # Not from the data: a sentence ending in a link.
    assert find_links("The recipe is at https://plantyou.com/vegan-taquitos/.", []) == [
        Link("https://plantyou.com/vegan-taquitos/", "The recipe is at")
    ]


@pytest.mark.parametrize(
    ("url", "skipped"),
    [
        ("https://www.instagram.com/reel/DGYYpsWpzik/?hl=en", True),
        ("https://vt.tiktok.com/ZSYAxFagf/", True),  # a subdomain of a skipped site
        ("https://de.pinterest.com/pin/1038150151606228580/", True),
        ("https://www.theedgyveg.com/2023/04/24/3-ingredient-vegan-brownies/", False),
        ("https://bit.ly/3RflF7w", False),  # checked again once it's followed
        ("https://notx.com/", False),  # Not from the data: x.com is a whole name
    ],
)
def test_is_skipped(url: str, skipped: bool) -> None:
    assert is_skipped(url) is skipped
