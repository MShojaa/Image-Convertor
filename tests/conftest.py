"""Shared fixtures.

The important one is not shared state between tests -- it is that the tests
must never touch the real settings file. `settings.folder()` resolves from the
environment every call, so pointing those variables at a tmp folder for every
test is enough, and it is done automatically rather than per test: a test that
forgot would write to the developer's own profile and pass, and the next run
would read it back and fail somewhere else entirely. That happened once.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    """Every test gets its own empty settings folder."""
    store = tmp_path / "profile"
    monkeypatch.setenv("LOCALAPPDATA", str(store))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(store))
    return store
