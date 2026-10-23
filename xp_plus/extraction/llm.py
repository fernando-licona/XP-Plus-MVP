from __future__ import annotations

from pathlib import Path

from .base import Extraction


class LLMExtractor:
    """Paper (PDF + SI) -> Extraction via an LLM. NOT IMPLEMENTED YET.

    Contract the implementation must meet (the full checklist the prompt should follow is
    .claude/skills/paper-extraction/SKILL.md):
    - Output validates as `Extraction` (use its JSON schema as the structured-output schema).
    - Every value is tagged: `paper_stated` with a quote + section/page in `source`, or
      `inferred` with the reasoning in `note`. Never invent a value as `paper_stated`.
    - Anything the procedure needs but the paper omits is left `missing` and listed as a Gap
      with `detected_by="extraction"`.
    - Open decisions (SCOPE.md §9): which model, and whether paper content may leave the
      machine. FlowLab's own extractor (backend/papers/extract.py) is a reference, but its
      schema has no provenance or gaps.
    - Score it against the FixtureExtractor's hand-annotated version of the target paper.
    """

    def __init__(self, model: str | None = None):
        self.model = model

    def extract(self, source: str | Path) -> Extraction:
        raise NotImplementedError("LLM extraction is not implemented yet; use FixtureExtractor")
