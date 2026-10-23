"""Stage 1: paper -> PaperFeatures + the gaps the extractor noticed."""
from .base import Extraction, Extractor
from .fixture import FixtureExtractor
from .llm import LLMExtractor

__all__ = ["Extraction", "Extractor", "FixtureExtractor", "LLMExtractor"]
