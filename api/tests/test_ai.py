import json

import httpx2
import pytest

from recipes.ai import MODEL, SYSTEM_PROMPT, AIError, Claude, VideoText
from recipes.chapters import parse_chapters

from fakes import FakeClaudeApi, read_fixture

WHR7_TITLE = read_fixture("videos.json")["items"][0]["snippet"]["title"]


def whr7(*, with_chapters: bool = True) -> VideoText:
    """The meal prep video, with its full description."""
    description = read_fixture("descriptions.json")["whr7iOKRXTA"]
    return VideoText(
        title=WHR7_TITLE,
        description=description,
        chapters=parse_chapters(description) if with_chapters else [],
        creator_comments=[],
    )


@pytest.fixture
def fake_claude() -> FakeClaudeApi:
    return FakeClaudeApi()


def find_recipes(fake: FakeClaudeApi, video: VideoText):  # type: ignore[no-untyped-def]
    with Claude("test-key", transport=fake.transport) as claude:
        return claude.find_recipes(video)


def test_finds_the_recipes_in_a_video(fake_claude: FakeClaudeApi) -> None:
    reply = find_recipes(fake_claude, whr7())

    assert reply.answer is not None
    assert [(r.name, r.chapter) for r in reply.answer.recipes] == [
        ("Overnight oats", 1),
        ("Mexican inspired salad", 2),
        ("Sticky lemon & garlic tofu", 3),
        ("Hearty vegan lasagne", 4),
        ("Raspberry oat bars", 5),
    ]
    assert (reply.stop_reason, reply.input_tokens, reply.output_tokens) == (
        "end_turn",
        3310,
        206,
    )


def test_sends_the_video_in_tags_with_numbered_chapters(
    fake_claude: FakeClaudeApi,
) -> None:
    find_recipes(fake_claude, whr7())

    body = json.loads(fake_claude.requests[0].content)
    assert body["model"] == MODEL
    assert body["system"] == SYSTEM_PROMPT
    message = body["messages"][0]["content"]
    assert message.startswith(f"<title>{WHR7_TITLE}</title>\n<chapters>\n0. [0:00] ")
    assert "<creator_comments>\n(none)\n</creator_comments>" in message
    assert fake_claude.requests[0].headers["Authorization"] == "Bearer test-key"


def test_chapters_the_video_doesnt_have_are_dropped(
    fake_claude: FakeClaudeApi,
) -> None:
    # The real reply names chapters 1-5, but this copy of the video has none.
    reply = find_recipes(fake_claude, whr7(with_chapters=False))

    assert reply.answer is not None
    assert [r.chapter for r in reply.answer.recipes] == [None] * 5


def test_a_refusal_leaves_no_answer(fake_claude: FakeClaudeApi) -> None:
    """Not from the data: no video has been refused, so this reply is made up."""
    refusal = {**read_fixture("claude_replies.json")["whr7iOKRXTA"]}
    refusal |= {"content": [], "stop_reason": "refusal"}
    fake_claude.queue.append(httpx2.Response(200, json=refusal))

    reply = find_recipes(fake_claude, whr7())

    assert (reply.answer, reply.stop_reason) == (None, "refusal")


def test_a_cut_off_answer_is_asked_for_again_with_more_room(
    fake_claude: FakeClaudeApi,
) -> None:
    """Not from the data: no answer has been cut off, so this reply is made up."""
    cut_off = {**read_fixture("claude_replies.json")["whr7iOKRXTA"]}
    cut_off |= {"content": [{"type": "text", "text": '{"reci'}]}
    cut_off |= {"stop_reason": "max_tokens"}
    fake_claude.queue.append(httpx2.Response(200, json=cut_off))

    reply = find_recipes(fake_claude, whr7())

    assert reply.answer is not None
    first, second = (json.loads(r.content) for r in fake_claude.requests)
    assert second["max_tokens"] == first["max_tokens"] * 2


def test_an_api_error_raises_an_ai_error(fake_claude: FakeClaudeApi) -> None:
    """Not from the data: the error follows the shape in Anthropic's error docs."""
    error = {
        "type": "error",
        "error": {"type": "invalid_request_error", "message": "Bad request"},
    }
    fake_claude.queue.append(httpx2.Response(400, json=error))

    with pytest.raises(AIError):
        find_recipes(fake_claude, whr7())
