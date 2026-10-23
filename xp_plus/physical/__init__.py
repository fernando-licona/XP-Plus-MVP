"""Public MVP: recorded observations only. No hardware/control client is shipped."""
from typing import Protocol
from ..schema import PaperFeatures, PhysicalRecord
from .recorded import RecordedRunner
class PhysicalRunner(Protocol):
    def run(self, f: PaperFeatures) -> PhysicalRecord: ...
__all__ = ["PhysicalRunner", "RecordedRunner"]
