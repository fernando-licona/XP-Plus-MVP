from __future__ import annotations

from pathlib import Path

from ..schema import PaperFeatures, PhysicalRecord


class RecordedRunner:
    """Observations from a run done outside the pipeline (bench notebook, earlier FlowLab run).

    The file is a PhysicalRecord as JSON. Also the demo fallback if the rig isn't ready.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def run(self, f: PaperFeatures) -> PhysicalRecord:
        return PhysicalRecord.model_validate_json(self.path.read_text(encoding="utf-8"))
