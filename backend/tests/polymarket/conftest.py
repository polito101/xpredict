"""Polymarket test fixtures — VCR fixture loaders for Gamma API responses."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "gamma"


def load_gamma_fixture(name: str) -> dict:
    """Load a JSON fixture from backend/tests/fixtures/gamma/{name}.json."""
    fixture_path = FIXTURES_DIR / f"{name}.json"
    return json.loads(fixture_path.read_text(encoding="utf-8"))


@pytest.fixture
def gamma_active() -> dict:
    return load_gamma_fixture("active_market")


@pytest.fixture
def gamma_closed_not_resolved() -> dict:
    return load_gamma_fixture("closed_not_resolved")


@pytest.fixture
def gamma_disputed() -> dict:
    return load_gamma_fixture("disputed_market")


@pytest.fixture
def gamma_resolved() -> dict:
    return load_gamma_fixture("resolved_market")


# Phase 14 — Curated Per-Category Gamma Sync fixtures.
# NOTE: ``load_gamma_fixture`` returns ``json.loads(...)`` which for these three
# fixtures is a LIST (the /events array / /tags array), not a dict. The loader
# works unchanged; only the return type differs.
@pytest.fixture
def gamma_events_multi() -> list[dict]:
    """One Crypto event with 3 Bitcoin-ladder children (grouping path)."""
    return load_gamma_fixture("events_multi_outcome")


@pytest.fixture
def gamma_events_single() -> list[dict]:
    """One Politics/World event, len==1, dual-tagged (EVT-07 standalone path)."""
    return load_gamma_fixture("events_single_market")


@pytest.fixture
def gamma_tags_categories() -> list[dict]:
    """The 7 verified category {id, label, slug} tags."""
    return load_gamma_fixture("tags_categories")
