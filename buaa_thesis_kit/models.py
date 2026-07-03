from __future__ import annotations

import copy
from dataclasses import asdict, dataclass, field
from typing import Any, Literal


Status = Literal["draft", "pass", "needs_review", "failed"]


@dataclass
class SourceEvidence:
    file: str
    method: str
    paragraph_index: int | None = None
    page_hint: int | None = None
    confidence: float = 0.0
    requires_review: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Metadata:
    title_cn: str = ""
    title_en: str = ""
    student_name: str = ""
    student_id: str = ""
    college: str = ""
    major: str = ""
    advisor: str = ""
    date: str = ""
    classification: str = ""
    unit_code: str = "10006"
    evidence: dict[str, SourceEvidence] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["evidence"] = {k: v.to_dict() for k, v in self.evidence.items()}
        return data


@dataclass
class ContentBlock:
    id: str
    type: str
    title: str = ""
    text: str = ""
    level: int = 0
    source: SourceEvidence | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["source"] = self.source.to_dict() if self.source else None
        return data


@dataclass
class AssetItem:
    id: str
    type: str
    path: str
    caption: str = ""
    source: SourceEvidence | None = None
    requires_review: bool = False

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["source"] = self.source.to_dict() if self.source else None
        return data


@dataclass
class EquationItem:
    id: str
    kind: str
    text: str = ""
    number: str = ""
    latex: str = ""
    omml: str = ""
    preview_path: str = ""
    source: SourceEvidence | None = None
    requires_review: bool = True

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["source"] = self.source.to_dict() if self.source else None
        return data


@dataclass
class ThesisModel:
    metadata: Metadata = field(default_factory=Metadata)
    front_matter: dict[str, Any] = field(default_factory=dict)
    sections: list[ContentBlock] = field(default_factory=list)
    figures: list[AssetItem] = field(default_factory=list)
    tables: list[ContentBlock] = field(default_factory=list)
    equations: list[EquationItem] = field(default_factory=list)
    references: list[ContentBlock] = field(default_factory=list)
    appendices: list[ContentBlock] = field(default_factory=list)
    extraction_warnings: list[str] = field(default_factory=list)
    status: Status = "draft"

    def to_dict(self) -> dict[str, Any]:
        return {
            "metadata": self.metadata.to_dict(),
            "front_matter": copy.deepcopy(self.front_matter),
            "sections": [x.to_dict() for x in self.sections],
            "figures": [x.to_dict() for x in self.figures],
            "tables": [x.to_dict() for x in self.tables],
            "equations": [x.to_dict() for x in self.equations],
            "references": [x.to_dict() for x in self.references],
            "appendices": [x.to_dict() for x in self.appendices],
            "extraction_warnings": copy.deepcopy(self.extraction_warnings),
            "status": self.status,
        }
