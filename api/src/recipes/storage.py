"""Where fetched playlists are kept. All storage goes through this module.

For now that's a JSON file. In Phase 2 it becomes SQLite, and only this file changes.
"""

import json
from dataclasses import asdict
from pathlib import Path

from recipes.playlist import Playlist


def save_playlist(playlist: Playlist, path: Path) -> None:
    """Write the playlist to a JSON file."""
    data = {
        "playlist_id": playlist.id,
        "unavailable_count": playlist.unavailable_count,
        "videos": [asdict(video) for video in playlist.videos],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, indent=2, ensure_ascii=False)
    path.write_text(text + "\n", encoding="utf-8")
