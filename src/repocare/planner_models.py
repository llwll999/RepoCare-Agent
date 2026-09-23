from pydantic import BaseModel, Field


class EvidenceItem(BaseModel):
    source: str
    observation: str = Field(min_length=3, max_length=300)


class Hypothesis(BaseModel):
    statement: str = Field(min_length=10, max_length=300)
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: list[EvidenceItem] = Field(default_factory=list)


class ProposedChange(BaseModel):
    file_path: str
    summary: str = Field(min_length=5, max_length=300)
    requires_approval: bool = True


class DiagnosisPlan(BaseModel):
    hypotheses: list[Hypothesis] = Field(min_length=1, max_length=3)
    unknowns: list[str] = Field(default_factory=list)
    proposed_changes: list[ProposedChange] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)