# Test fixtures

Trimmed copies of real YouTube Data API responses for the playlist, captured on 20 Nov 2026. Only the fields the code reads are kept.

- **`videos.json`:** five real videos from the playlist, with descriptions cut to their first lines.
- **`descriptions.json`:** the full, untrimmed descriptions of two of those videos, keyed by video ID, for the chapter parser.
- **`playlist_items_page_1.json`, `playlist_items_page_2.json`:** seven real playlist items split across two pages. One video is deleted and one is private.
- **`error_playlist_not_found.json`:** a real 404 response, for a playlist ID that doesn't exist.
- **`error_quota_exceeded.json`:** the only one not captured, because it can't be triggered safely. It follows the `quotaExceeded` example in [Google's error docs](https://developers.google.com/youtube/v3/docs/errors).
