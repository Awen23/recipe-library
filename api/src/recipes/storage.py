"""Where fetched playlists are kept. All storage goes through this module.

For now that's a JSON file. In Phase 2 it becomes SQLite, and only this file changes.
"""

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from recipes.chapters import parse_chapters
from recipes.playlist import Playlist
from recipes.youtube import Video


def save_playlist(playlist: Playlist, path: Path) -> None:
    """Write the playlist to a JSON file."""
    data = {
        "playlist_id": playlist.id,
        "unavailable_count": playlist.unavailable_count,
        "videos": [_video_data(video) for video in playlist.videos],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, indent=2, ensure_ascii=False)
    path.write_text(text + "\n", encoding="utf-8")


def _video_data(video: Video) -> dict[str, Any]:
    """A video's fields, plus the chapters found in its description."""
    chapters = parse_chapters(video.description)
    return asdict(video) | {"chapters": [asdict(chapter) for chapter in chapters]}
