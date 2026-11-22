# Test fixtures

Trimmed copies of real YouTube Data API responses for the playlist, captured on 20 Nov 2026. The thumbnails, embedding and channel IDs in `videos.json` were added on 22 Nov 2026. Only the fields the code reads are kept.

- **`videos.json`:** five real videos from the playlist, with descriptions cut to their first lines.
- **`comment_threads.json`:** the first three of the top comments on `eG0tXlljTtI`. The first is by the video's channel. The other two are by viewers, so their channel IDs are replaced with random IDs of the same shape.
- **`descriptions.json`:** the full, untrimmed descriptions of three of those videos, keyed by video ID, for the chapter parser.
- **`playlist_items_page_1.json`, `playlist_items_page_2.json`:** seven real playlist items split across two pages. One video is deleted and one is private.
- **`error_playlist_not_found.json`:** a real 404 response, for a playlist ID that doesn't exist.
- **`error_quota_exceeded.json`:** not captured, because it can't be triggered safely. It follows the `quotaExceeded` example in [Google's error docs](https://developers.google.com/youtube/v3/docs/errors).
- **`error_comments_disabled.json`:** not captured, because no video in the playlist has its comments turned off. It follows the `commentsDisabled` error in the [`commentThreads.list` docs](https://developers.google.com/youtube/v3/docs/commentThreads/list#errors).
- **`claude_replies.json`:** Claude's real replies (Claude Haiku 5.5, prompt version 1) for the five videos in `videos.json`, captured on 22 Nov 2026 and keyed by video ID. Each was asked about the video's full description, chapters and creator comments. Only the fields the code reads are kept: Claude's hidden reasoning (a `thinking` block) and the detailed usage are left out.
- **`pages/`:** three real recipe pages that fixture videos link to, captured on 22 Nov 2026. Each is cut down to its first Recipe object, with only the fields the code reads (name, ingredients and steps), and none of the site's own writing. `blueberry_baked_oatmeal.html` and `west_african_peanut_stew.html` hold JSON-LD. `vegan_brownies.html` holds Microdata, the older way of marking up a recipe.
- **`claude_details_replies.json`:** Claude's real replies (Claude Haiku 5.5) when asked where the recipes of `nHr9LqK3PKc` and `whr7iOKRXTA` are written, captured on 22 Nov 2026 and keyed by video ID. They're the two fixture videos plain code can't settle. Each was asked with the full description and the links as the tests fetch them, where only the pages in `pages/` answer. They're trimmed the same way as `claude_replies.json`.
