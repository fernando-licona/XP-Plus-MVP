from __future__ import annotations

from pathlib import Path

from .base import Extraction


class FixtureExtractor:
    """Loads a hand-annotated extraction (JSON). Used for tests, demos and scoring the LLM."""

    def extract(self, source: str | Path) -> Extraction:
        return Extraction.model_validate_json(Path(source).read_text(encoding="utf-8"))
