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
1. **Understand the playlist.** Fetch it, and measure what's actually there: how recipes are split across videos, how Shorts differ, and where recipe details live. *(Done: findings in Section 4.)*
2. **Useful info for every recipe.** Split each video into its recipes, each with a name, a start time where there is one, and its ingredients and method wherever they can be found. Plain code does what it can, and AI does the parts Phase 1 showed plain code can't. *(Planned in Section 5.)*
3. **Rating and sorting.** Hide the recipes in a multi-recipe video that I'm not interested in, and rate my interest in the rest, so the library can be filtered down to what I'd actually cook.
4. **The UI.** A deployed web app (Python API, React + TypeScript frontend) for searching, filtering and rating the library.

## 3. Later
Ideas deferred while we focus on the current phase. Added to as we discuss and defer things.
- **Videos that aren't recipes** (a talk, a haul): they're kept as one recipe named after the video, so they can be found. The UI could hide them, and they could get a better name than the video's title.
- **Refreshing the library from the app** (e.g. a "refresh playlist" button), instead of running a fetch command.
- **robots.txt:** check each site's before fetching its pages. Every link is one a creator chose, so for now they're fetched like a person following them would.
- **Links that failed** (a timeout, a busy site) are fetched once and not tried again.
- **Searchable ingredient names**, such as "leeks" from "1-2 leeks, chopped or a few handfuls spinach", for the UI's search. Ingredient lines are kept as written for now.
- **A dish made to go inside another** (meatballs for a meatball sub) is sometimes listed as two recipes. Splitting could merge them.
- **Links to other videos** (YouTube, TikTok, Instagram): some creators link the video a recipe was shown in. That video's description could be read for the ingredients.
- **Addresses behind hostnames:** links to this computer or to private IP addresses are refused, but a hostname that resolves to one isn't checked yet. Add it before the app is hosted.
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

**PR 2: Fetch and chapters** *(done, the only code kept from this phase)*
- *Before starting:* the playlist is set to unlisted, and a YouTube Data API key exists.
- A `recipes fetch <playlist-id>` command (the ID isn't a secret): pages through `playlistItems.list`, then fetches details with `videos.list` in batches of 50 (title, description, duration, publish date, channel). Deleted or private videos are skipped and counted.
- The results are saved as a git-ignored JSON file. No database yet.
- A chapter parser: description text in, list of chapters (start time in seconds, title) out, handling the formats the real descriptions use.
- Tests never call the live API. They use small fixtures in `tests/fixtures/`: trimmed copies of real API responses (a few videos, with the playlist ID replaced) and real description lines.
  - **Fetch:** follows `nextPageToken` across pages; batches IDs into groups of 50; skips and counts deleted or private videos; converts YouTube's durations (`PT19M17S` → 1157 seconds); gives a clear error for a missing key or exhausted quota.
  - **Chapter parser:** one table of description text → expected chapters. The cases are chosen once we've seen what the real descriptions look like.
- *Done when:* every available video is in the JSON file with its chapters, and the tests pass.

**Then: exploration** *(done, not a PR)*
Claude labelled every video, using throwaway scripts outside the repo: first from the title, description and chapters, then again with the top 20 comments for the uncertain ones. Instead of checking every uncertain video, I spot-checked the 10 least certain. They matched the labels, so the labels are trusted as a general picture. They're kept in the git-ignored `api/data/exploration/`.

### Findings
Counts are from the 434 available videos. "Shorts" means 3 minutes or less, because the API doesn't mark them.

1. **Multi-recipe videos:** 81 videos hold about 400 recipes, so the playlist has about 740 recipes in all.
   - 76 of the 81 are long-form, so 64% of long videos are multi-recipe. Only 5 are Shorts.
   - 56 of the 81 have chapters in their description.
2. **Chapters:**
   - In 38 of those 56, each chapter is one recipe, apart from intros and outros. "Intro" alone appears 55 times.
   - In the other 18, recipe chapters are mixed with steps or padding ("make the toppings", "errands interlude").
   - 49 long videos have no timestamps in their description, and 20 of them are multi-recipe. Some of these show YouTube's automatic chapters on the video.
3. **Shorts are different:** 304 of 315 are a single recipe, none have chapters, and 114 have an empty description. For a Short, the work is finding the recipe, not splitting the video.
4. **Where recipes live** (the first source found for each video):

   | Source | Shorts (315) | Long (119) |
   |---|---|---|
   | Description (ingredient list) | 71 | 53 |
   | Creator's comment | 60 | 1 |
   | Link to a recipe page | 84 | 54 |
   | App or paid | 12 | 3 |
   | Not found | 88 | 8 |

5. **Comments:** an API key can read them (1 quota unit per video). The creator's own comment is identifiable, because its author is the video's channel. It's the only source of the recipe for 60 Shorts.
6. **Where plain code falls short:**
   - **Plain code can:** fetch creator comments, skip intro and outro chapters, find ingredient lists, and pull out recipe links.
   - **Plain code can't:** tell recipe chapters from step chapters (18 videos), name the dish when the title is clickbait ("EVERYONE can like tofu!"), or find start times for videos with no timestamps in their description (20 videos). The comments often name the dish, and Claude's labels did this well.
7. **Linked recipe pages often have structured data:** 212 videos link to a page that isn't social media or a shop, checking up to 3 links each. For 119 of them, the page has schema.org `Recipe` data with an ingredient list, and for 100 of those the description has no ingredient list of its own. 74 pages had no recipe data (Substack posts, Google Docs, ebook shops, some blogs), and 19 were blocked or failed.
8. **Some videos are assemblies, not recipes** (for example a lunch box put together from ready foods). A recipe named after the video is enough for these.

## 5. Phase 2: useful info for every recipe

### Goal
Every video becomes one or more **recipes**, ready for rating (Phase 3) and the UI (Phase 4). Each recipe has:
- a name
- its video
- a start time, or none if the description has no timestamp for it
- its **details** where they can be found: an **ingredients** list and a **method**
- where the details came from: the description, the creator's comment, or a link. When they couldn't be read (an app, a paywall, or a page without recipe data), the link is where to find them.

Each video also keeps its **thumbnail**, its **channel**, and whether it can be **embedded** in a page. Whether it's a **Short** is worked out from its length.

### How the data is kept
- **Fetched data and recipes are kept apart.** Videos, comments and fetched recipe pages are stored as they arrived. Recipes are worked out from them, so working them out never needs another fetch.
- **Fetching and building again only add new videos and their recipes.** Stored videos and recipes are left as they are, since they're already in use. A video that leaves the playlist is marked as removed, not deleted, and its recipes go with it.
- **Each recipe gets an ID when it's created, and keeps it,** so Phase 3's ratings stay attached.
- **Each field records who set it:** plain code, AI (with how sure it was), or a correction I made by hand. Building never overwrites a stored field: it only fills in details that are still empty, so hand corrections are kept.
- **The tables are designed up front, and each PR creates the ones it fills,** with an Alembic migration. All database access goes through `storage.py`.

### Tables
Fetched, created in PR 1:
- **`channels`:** YouTube's channel ID and the channel's title.
- **`videos`:** the title, description, length, publish date, thumbnail, whether it can be embedded, its channel, when it was first seen, and when it was removed from the playlist, if it was.
- **`chapters`:** each video's chapters in order, parsed from its description.
- **`creator_comments`:** the comments posted by the video's own channel.

Worked out, created in later PRs:
- **`recipes`** (PR 2) holds what a recipe card shows:
  - `id` (never reused), `video_id` and `position` within the video (unique together), and `chapter_position`, the chapter it starts in
  - `name`, with `name_by` and `name_confidence`
  - `start_seconds`, with `start_by`
  - Each `_by` is `code`, `ai` or `hand`. Code and AI skip any group whose `_by` is `hand`.
  - PR 3 adds the details: `ingredients` and `method` (JSON lists of lines and steps), `source` and `source_url`, with one `details_by` and `details_confidence` for all four.
- **`recipe_pages`** (PR 3): each linked page as fetched: its URL, the words beside the link, where it redirected to, when it was fetched, what was found (such as `recipe`, `no recipe data` or `HTTP 403`), and the name, ingredients and steps of its first schema.org `Recipe`. The page itself isn't kept.

### PRs
An outline only. Each PR is planned in detail before it starts, and its architecture decisions are made then, such as which AI model to use. Each PR uses AI where plain code can't do the job, so no PR leaves recipes half-right. The first PR to use AI sets it up.

**1. Fetched data in SQLite** *(done)*
- SQLite through SQLAlchemy Core, with tables created and changed by Alembic migrations.
- `recipes fetch <playlist-id>` stores new videos with their channels, chapters and creator comments, and marks videos that have left the playlist as removed.
- *Plain code only.*

**2. Recipes** *(done)*
- `recipes build` splits each video fetched since the last build into recipes (every video gets at least one), asking Claude once per video. Recipes already stored are never changed.
- **AI** (Claude Haiku 5.5, one structured answer per video): lists the recipes the video teaches, in order, with each one's name and the chapter it starts in. This covers telling recipe chapters from step chapters or padding (such as "make the toppings" or "errands interlude"), chapters that hold several recipes, multi-recipe videos with no timestamps, and naming dishes from clickbait titles using the description and the creator's comments.
- **Plain code:** a recipe starts where its chapter starts. When a chapter holds several recipes, only the first gets the start. A video where Claude finds no recipe is one recipe named after the video, so every video can be found. Without an answer (Claude declined), each chapter is a recipe named after the chapter.
- *Model:* Haiku 5.5, Sonnet 5.5 and Opus 5.5 were compared on 30 labelled videos, picked by type. Haiku matched as many recipe counts as Opus, so the cheapest model is used.

**3. Details** *(done)*
Each recipe's ingredients and method, from a linked page, the description or a creator comment. Linked pages come first: they're the most common source, and their recipe data needs no AI to read.
- `recipes fetch` also fetches the links in new videos' descriptions and creator comments, skipping social media, shops and sponsors, and keeps what each led to in `recipe_pages`. A video's links are fetched once. Requests to the same site are at least 1.5 s apart, a busy site gets one retry, and a page that asks for a browser check is left alone.
- **Plain code:** recipe-scrapers reads each page's schema.org `Recipe` data, in JSON-LD or Microdata. A video with one recipe and a link to a page with recipe data takes that page. A video with no readable link and no ingredient-like lines (amounts such as "2 tbsp" or "400g", or an "Ingredients" heading) is marked as looked at, without asking AI.
- **AI** (Claude Haiku 5.5, one structured answer per remaining video): for each recipe, picks the link whose page holds it, or copies its ingredient lines and method from the description or a creator comment. This covers names in another language from the links ("kåldolmar" for cabbage dumplings), one link for all of a video's recipes, matching lines to the right recipe when one description covers several, and leaving out lines that aren't ingredients ("Save 10% on…"). A page's ingredients are read from the page, not copied by AI, and a line AI copies is kept only if it's really in the text.
- Each recipe's details are looked for once: `details_by` says who looked, even when nothing was found.

*Done when:* the numbers roughly match what Phase 1 found, so anything the code misses shows up.
- **Recipes:** about 740, and every available video has at least one.
- **Ingredients:** found for about as many videos as Phase 1 found, from each source: about 120 from descriptions, 60 from creator comments and 120 from linked pages.
- **Agreement:** on 30 videos picked by type (12 with chapters, 5 multi-recipe without timestamps, 13 others) and checked by hand, the number of recipes matches for at least 27.
- **Fetching and building again:** add only new videos' recipes, and leave stored recipes untouched.
- **AI-made fields** are marked as AI-made, and the tests pass.
