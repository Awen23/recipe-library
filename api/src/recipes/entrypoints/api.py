"""The HTTP API, which the UI calls. Run it locally with `fastapi dev`.

Routes are plain `def`, not `async def`, because the database engine is synchronous:
FastAPI runs `def` routes in a thread pool, so a slow query doesn't hold up others.
See https://fastapi.tiangolo.com/async/
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Annotated, Any, TypedDict

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import Engine

from recipes import storage
from recipes.models import Interest, Marks, Verdict


class State(TypedDict):
    """What the app keeps while it runs, handed to each request."""

    engine: Engine


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[State]:
    """Runs when the app starts and stops: it opens the database, and closes it.
    What it yields is copied into each request's `state`. See
    https://fastapi.tiangolo.com/advanced/events/
    """
    load_dotenv()  # DATABASE_URL, if api/.env sets one
    engine = storage.create_engine()
    try:
        if storage.needs_migrating(engine):
            raise RuntimeError(
                "The database isn't up to date. Run `alembic upgrade head`."
            )
        yield {"engine": engine}
    finally:
        engine.dispose()


app = FastAPI(title="Recipe Library", lifespan=lifespan)


def get_engine(request: Request) -> Engine:
    engine: Engine = request.state.engine
    return engine


# A route asks for the engine by taking a parameter of this type, and FastAPI calls
# `get_engine` to fill it in.
DatabaseEngine = Annotated[Engine, Depends(get_engine)]


# What the API sends and receives. These are kept apart from the app's own types
# in `models`, so the API's shape only changes on purpose.


class InterestBody(BaseModel):
    interest: Interest | None  # null clears it


class VerdictBody(BaseModel):
    verdict: Verdict | None  # null clears it


class MarksResponse(BaseModel):
    interest: Interest | None
    verdict: Verdict | None
    updated_at: datetime  # UTC

    @classmethod
    def of(cls, marks: Marks) -> MarksResponse:
        return cls(
            interest=marks.interest,
            verdict=marks.verdict,
            updated_at=marks.updated_at,
        )


NOT_FOUND: dict[int | str, dict[str, Any]] = {
    404: {"description": "No recipe has this ID."}
}


@app.put("/recipes/{recipe_id}/interest", responses=NOT_FOUND)
def set_interest(
    recipe_id: int, body: InterestBody, engine: DatabaseEngine
) -> MarksResponse:
    """Set how interested I am in a recipe before cooking it, or clear it with
    null. "not_for_me" hides it from the library."""
    return MarksResponse.of(storage.set_interest(engine, recipe_id, body.interest))


@app.put("/recipes/{recipe_id}/verdict", responses=NOT_FOUND)
def set_verdict(
    recipe_id: int, body: VerdictBody, engine: DatabaseEngine
) -> MarksResponse:
    """Set how often I'd cook a recipe again after cooking it, or clear it with
    null."""
    return MarksResponse.of(storage.set_verdict(engine, recipe_id, body.verdict))


@app.exception_handler(storage.NoSuchRecipeError)
def no_such_recipe(_request: Request, error: storage.NoSuchRecipeError) -> JSONResponse:
    # The same shape as FastAPI's own errors.
    return JSONResponse({"detail": f"No recipe has the ID {error}."}, status_code=404)
