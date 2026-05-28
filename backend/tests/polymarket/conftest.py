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
