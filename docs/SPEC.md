# Recipe Library: Spec

*What we're building, the phases it's built in, and the next phase in detail. How we work is in [CLAUDE.md](../CLAUDE.md).*

## 1. Overview
I save cooking videos to a YouTube playlist, and it's become a poor source of recipes: **it's too unruly to look through** when I want something to cook. Three main things make it unruly:
1. **Volume.** There are 436 videos, and YouTube loads them a page at a time with no search across what's inside them.
2. **Multi-recipe videos.** In a "4 recipes" video I may only care about one or two, and finding them again means scrubbing through.
3. **Mixed interest.** Some saved recipes I'd cook again, and some I'm only mildly curious about, all in one undifferentiated list.

**Goal:** a fast, searchable library, ideally with **one entry per recipe rather than per video**, where each entry deep-links to the moment the recipe starts (`https://youtu.be/<id>?t=<seconds>`).

I don't yet know what the data looks like, so the plan starts by finding out. Only the next phase is planned in detail. Later phases are shaped by what the earlier ones find.

## 2. Phases
1. **Understand the playlist.** Fetch it, and measure what's actually there: how recipes are split across videos, how Shorts differ, and where recipe details live. *(Planned in Section 4.)*
2. **A searchable library.** A deployed web app (Python API, React + TypeScript frontend) built from what Phase 1 found, using plain code wherever plain code does the job.
3. **Fill the gaps.** Improve where Phase 2 falls short (e.g. searching by ingredient), with whichever approach the data shows works. That may be plain code, or it may be AI if it's genuinely needed.

## 3. Later
Ideas deferred while we focus on the current phase. Added to as we discuss and defer things.
- **Mixed interest:** marking recipes I'd cook again, and filtering by it.
- **Refreshing the library from the app** (e.g. a "refresh playlist" button), instead of running a fetch command.
- **The data model** is designed in Phase 2, once Phase 1 shows what the data looks like. It's stored in SQLite.
- **Other people's playlists:** sign in with Google (`youtube.readonly` scope, which needs Google's app verification for a public launch). Before anyone else uses the app, move from SQLite to Postgres.

Out of scope: transcripts and audio (official captions only work for your own videos, and scrapers break YouTube's terms), and dietary filters.

## 4. Phase 1: understand the playlist

### Goal
Know what the 436 videos actually contain, well enough to decide what Phase 2 builds. Claude labels every video, and then I check two groups by hand: 1. any it's less than 90% sure of, and 2. a random 5% of the rest.

### Questions this phase answers
1. How many videos are multi-recipe, and **how many of those have chapters?**
2. In multi-recipe videos with chapters, is each chapter one recipe, or are chapters often steps or padding ("Intro", "Make the sauce")?
3. Do Shorts and long-form videos need to be handled differently?
4. Where do ingredients and methods commonly live: the description, a link to a blog, the creator's comments, or nowhere?
5. Can the creator's comments be read (the playlist is unlisted, and we only have an API key), and are they useful?
6. Given all that, where does plain code fall short, and is AI useful for any of it?

### PRs
Only code worth keeping is merged. Exploration isn't a PR.

**PR 1: Skeleton** *(done)*
- *Before starting:* Python 3.14 is installed.
- Python project set up with `pip` and a virtual environment; `pytest` for tests and `ruff` for lint and format.
- `.gitignore` (`.env`, cached data, caches) and `.env.example` (`YOUTUBE_API_KEY`).
- A PR template with the three sections from `CLAUDE.md`.
- *Done when:* a placeholder test and the linter both pass, each with one command.

**PR 2: Fetch and chapters** *(next, the only code kept from this phase)*
- *Before starting:* the playlist is set to unlisted, and a YouTube Data API key exists.
- A `recipes <playlist-id>` command (the ID isn't a secret): pages through `playlistItems.list`, then fetches details with `videos.list` in batches of 50 (title, description, duration, publish date, channel). Deleted or private videos are skipped and counted.
- The results are saved as a git-ignored JSON file. No database yet.
- A chapter parser: description text in, list of chapters (start time in seconds, title) out, handling the formats the real descriptions use.
- Tests never call the live API. They use small fixtures in `tests/fixtures/`: trimmed copies of real API responses (a few videos, with the playlist ID replaced) and real description lines.
  - **Fetch:** follows `nextPageToken` across pages; batches IDs into groups of 50; skips and counts deleted or private videos; converts YouTube's durations (`PT19M17S` → 1157 seconds); gives a clear error for a missing key or exhausted quota.
  - **Chapter parser:** one table of description text → expected chapters. The cases are chosen once we've seen what the real descriptions look like.
- *Done when:* every available video is in the JSON file with its chapters, and the tests pass.

**Then: exploration** *(not a PR)*
Claude works through the fetched data directly, using throwaway scripts outside the repo, and reports back:
- the answers to the questions above, with counts
- a label for every video, with a confidence
- for me to check: every video under 90% confidence, plus a random 5% of the rest
- a short sample of the comments API on a few videos (Question 5)

I check those videos, the answers are corrected where I disagree, and the findings are written into this spec along with an outline of Phase 2.
