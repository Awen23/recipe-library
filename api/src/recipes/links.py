"""Find the links in a video's description and creator comments that may lead to a
written recipe."""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from urllib.parse import urlsplit

# Sites that never hold a written recipe. A link to one of them, or to a subdomain of
# one, is skipped. Picked from the sites the playlist's videos link to.
SKIPPED_SITES = (
    # Social media and video
    "bsky.app",
    "discord.com",
    "discord.gg",
    "facebook.com",
    "fb.me",
    "instagram.com",
    "lemon8-app.com",
    "pinterest.ca",
    "pinterest.com",
    "reddit.com",
    "snapchat.com",
    "threads.com",
    "threads.net",
    "tiktok.com",
    "twitch.tv",
    "twitter.com",
    "x.com",
    "youtu.be",
    "youtube.com",
    # Music
    "artlist.io",
    "bandcamp.com",
    "epidemicsound.com",
    "musicbed.com",
    "soundcloud.com",
    "soundstripe.com",
    "spotify.com",
    "thmatc.co",
    # Shops and shopping links
    "amazon.ca",
    "amazon.co.uk",
    "amazon.com",
    "amazon.de",
    "amz.cx",
    "amzn.eu",
    "amzn.to",
    "barnesandnoble.com",
    "geni.us",
    "iherb.com",
    "indigo.ca",
    "liketoknow.it",
    "pxf.io",
    "sainsburys.co.uk",
    "shopltk.com",
    "shopmy.us",
    "sjv.io",
    "teepublic.com",
    "vinted.de",
    "waitrose.com",
    "walmrt.us",
    # Sponsors, sign-ups and support
    "audibletrial.com",
    "betterhelp.com",
    "buymeacoffee.com",
    "gofund.me",
    "gofundme.com",
    "ko-fi.com",
    "mailchi.mp",
    "patreon.com",
    "paypal.me",
    "saily.com",
    "skool.com",
    "squarespace.com",
    "surfshark.com",
    "yt.link",
    # Pages of links, not a redirect to one
    "linktr.ee",
)

_URL = re.compile(r"https?://[^\s<>\"'()\[\]]+")
_TRAILING = ".,!?;:"  # punctuation after a URL, not part of it
_AROUND_TEXT = " \t:-–—|•*→"  # what's left around a link's text once its URL is out


@dataclass(frozen=True)
class Link:
    url: str  # as written
    text: str  # the words on its line, or the line before when it's alone on its line


def find_links(description: str, creator_comments: Sequence[str]) -> list[Link]:
    """The links in a video's description, then its creator comments, in the order
    they're written, without repeats or skipped sites."""
    found: dict[str, Link] = {}
    for text in (description, *creator_comments):
        previous = ""
        for line in text.splitlines():
            words = _URL.sub("", line).strip(_AROUND_TEXT)
            for match in _URL.finditer(line):
                url = match.group().rstrip(_TRAILING)
                if url not in found and not is_skipped(url):
                    found[url] = Link(url, words or previous)
            previous = words
    return list(found.values())


def is_skipped(url: str) -> bool:
    """Whether `url` is on one of the skipped sites."""
    host = (urlsplit(url).hostname or "").lower()
    return any(host == site or host.endswith("." + site) for site in SKIPPED_SITES)
