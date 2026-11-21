"""Shared fixtures. pytest loads this file itself; tests use its fixtures by name."""

import pytest

from fakes import FakeYouTubeApi


@pytest.fixture
def fake_api() -> FakeYouTubeApi:
    return FakeYouTubeApi()
