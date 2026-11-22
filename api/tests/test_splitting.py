from recipes.ai import AIRecipe, VideoAnswer
from recipes.chapters import parse_chapters
from recipes.splitting import split_video

from fakes import read_fixture, recorded_answer

WHR7_CHAPTERS = parse_chapters(read_fixture("descriptions.json")["whr7iOKRXTA"])


def test_each_recipe_claude_found_starts_at_its_chapter() -> None:
    recipes = split_video("Meal prep", WHR7_CHAPTERS, recorded_answer("whr7iOKRXTA"))

    assert [(r.name, r.chapter_position, r.start_seconds) for r in recipes] == [
        ("Overnight oats", 1, 102),
        ("Mexican inspired salad", 2, 561),
        ("Sticky lemon & garlic tofu", 3, 685),
        ("Hearty vegan lasagne", 4, 857),
        ("Raspberry oat bars", 5, 1011),
    ]
    assert [r.position for r in recipes] == [0, 1, 2, 3, 4]
    assert {(r.name_by, r.start_by) for r in recipes} == {("ai", "ai")}
    assert recipes[0].name_confidence == 85


def test_a_video_without_chapters_has_recipes_with_no_start() -> None:
    recipes = split_video("Blueberry", [], recorded_answer("gOxwhuntyMY"))

    assert [(r.name, r.start_seconds) for r in recipes] == [
        ("Blueberry baked oatmeal", None)
    ]


def test_only_the_first_recipe_in_a_chapter_gets_its_start() -> None:
    """Not from the data: checks the rule, with a made-up answer."""
    answer = VideoAnswer(
        recipes=[
            AIRecipe(name="Overnight oats", chapter=1, confidence=90),
            AIRecipe(name="Tofu scramble", chapter=1, confidence=90),
        ],
        note="",
    )

    recipes = split_video("Meal prep", WHR7_CHAPTERS, answer)

    assert [(r.chapter_position, r.start_seconds) for r in recipes] == [
        (1, 102),
        (1, None),
    ]


def test_without_an_answer_each_chapter_is_a_recipe() -> None:
    recipes = split_video("Meal prep", WHR7_CHAPTERS, None)

    assert [(r.name, r.start_seconds) for r in recipes][:2] == [
        ("Intro", 0),
        ("Breakfasts", 102),
    ]
    assert len(recipes) == len(WHR7_CHAPTERS)
    assert {(r.name_by, r.start_by) for r in recipes} == {("code", "code")}


def test_a_video_with_no_recipes_found_is_one_named_after_it() -> None:
    """Not from the data: checks the rule, with a made-up empty answer."""
    title = read_fixture("videos.json")["items"][0]["snippet"]["title"]

    recipes = split_video(title, WHR7_CHAPTERS, VideoAnswer(recipes=[], note=""))

    assert [(r.name, r.name_by, r.start_seconds) for r in recipes] == [
        (title, "code", None)
    ]
