from dataclasses import dataclass
from enum import StrEnum


class ReviewStatus(StrEnum):
    APPROVED = "APPROVED"
    NEEDS_MORE_INFO = "NEEDS_MORE_INFO"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class ReviewRecord:
    material_id: str
    version: int
    status: ReviewStatus
    score: int
    superseded: bool = False