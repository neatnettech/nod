import pytest


@pytest.fixture(autouse=True)
def _no_nod_db(monkeypatch):
    """Every test (and every nod it shells out to) ignores a developer's NOD_DB unless the test sets one."""
    monkeypatch.delenv("NOD_DB", raising=False)
