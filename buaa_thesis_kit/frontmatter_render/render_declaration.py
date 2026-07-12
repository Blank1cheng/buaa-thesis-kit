from __future__ import annotations

from dataclasses import dataclass

from buaa_thesis_kit.models import Metadata


DECLARATION_TITLE = "本人声明"
REFERENCE_DECLARATION_TEXT = (
    "我声明，本论文及其研究工作是由本人在导师指导下独立完成的，"
    "在完成论文时所利用的一切资料均已在参考文献中列出。"
)


@dataclass(frozen=True)
class DeclarationModel:
    declaration_title: str
    declaration_text: str
    author_name: str
    date: str


def build_declaration_model(metadata: Metadata) -> DeclarationModel:
    return DeclarationModel(
        declaration_title=DECLARATION_TITLE,
        declaration_text=REFERENCE_DECLARATION_TEXT,
        author_name=metadata.student_name,
        date=metadata.date,
    )

