# Recipe Library

A recipe library; built to make some more sense out of my incredibly long YouTube recipe list. 

## Methodology 

Partly a place to relearn Python, partly a place to try out new ways of working with AI. Been trying out having a SPEC.md that defines what I'm doing and done. Started out with getting it to write commit-by-commit, give me challenges to complete myself, and explaining things in more detail so that I could learn more. Then, tried giving it more instructions and a way to work, then reviewed PRs instead. Once I get to UI, I'm going to try long-running agents and see how far it can get by itself and how it'll work with itself in iterations. 

## What's here

- `api/`: the Python side. It fetches the playlist from YouTube, asks Claude to split each video into its recipes and find their ingredients, stores them in SQLite, and serves them over a FastAPI API.
- `docs/SPEC.md`: what's being built, phase by phase.
- `web/`: the React UI, coming later.

## Setup

You need Python 3.14, and Docker only to re-lock dependencies (the command is in [CLAUDE.md](CLAUDE.md)). The commands below run in Git Bash on Windows from `api/`. On macOS or Linux, use `python3.14` instead of `py -3.14`, and `source .venv/bin/activate`.

```bash
cd api
py -3.14 -m venv .venv
source .venv/Scripts/activate        # in every new shell
pip install -e . --group dev         # the app, editable, plus the dev tools
pre-commit install                   # ruff and mypy on every commit
cp .env.example .env                 # then fill in the keys
alembic upgrade head                 # create the database, data/recipes.db
```

`api/.env` needs two keys:

- `YOUTUBE_API_KEY`: a YouTube Data API v3 key, from a Google Cloud project.
- `ANTHROPIC_API_KEY`: from https://platform.claude.com/settings/keys, used by `recipes build`.

It can also set `DATABASE_URL` to keep the database somewhere other than `data/recipes.db`.

## Running it

Fill the library from a playlist, then build the recipes:

```bash
recipes fetch <playlist-id>          # the ID after `list=` in the playlist's URL
recipes build                        # split the new videos into recipes, asking Claude
```

Both only do the new work, so they can be run again after adding videos to the playlist.

Then start the API:

```bash
fastapi dev
```

It reloads on changes, and its interactive docs are at http://127.0.0.1:8000/docs. If the database is behind, it won't start until you run `alembic upgrade head`.

## Checks

```bash
pytest                               # tests; they never use the network
ruff check .                         # lint
ruff format .                        # format
mypy                                 # type check
```

CI runs the same on every pull request.

After changing the tables in `src/recipes/storage.py`, write a migration with `alembic revision --autogenerate -m "describe the change"` and review it before committing.

