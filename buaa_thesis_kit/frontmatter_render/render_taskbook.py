from __future__ import annotations

from dataclasses import dataclass

from buaa_thesis_kit.models import Metadata, ThesisModel


TASK_BOOK_TITLE = "本科毕业设计（论文）任务书"
TASK_BOOK_UNIVERSITY = "北京航空航天大学"
TASK_SECTION_TITLE = "Ⅰ、毕业设计（论文）题目："
TASK_SECTION_RAW_MATERIALS = "Ⅱ、毕业设计（论文）使用的原始资料（数据）及设计技术要求："
TASK_SECTION_WORK_CONTENT = "Ⅲ、毕业设计（论文）工作内容："
TASK_SECTION_REFERENCES = "Ⅳ、主要参考资料："


@dataclass(frozen=True)
class TaskBookModel:
    title: str = ""
    raw_materials_and_requirements: str = ""
    work_content: str = ""
    references: str = ""
    college: str = ""
    major_class: str = ""
    student_name: str = ""
    thesis_date_range: str = ""
    defense_date: str = ""
    grade: str = ""
    advisor: str = ""
    department_director_signature: str = ""
    needs_review: bool = True


def build_task_book_model(model: ThesisModel) -> TaskBookModel:
    front = model.front_matter
    metadata = model.metadata
    raw_materials = _front_value(front, "task_raw_materials", "task_raw_materials_and_requirements")
    work_content = _front_value(front, "task_work_content")
    references = _front_value(front, "task_references")
    return TaskBookModel(
        title=_front_value(front, "task_title") or metadata.title_cn or metadata.title_en,
        raw_materials_and_requirements=raw_materials,
        work_content=work_content,
        references=references,
        college=_front_value(front, "task_college") or metadata.college,
        major_class=_front_value(front, "task_major_class") or metadata.major,
        student_name=metadata.student_name,
        thesis_date_range=_front_value(front, "task_date_range") or metadata.date,
        defense_date=_front_value(front, "defense_date"),
        grade=_front_value(front, "grade"),
        advisor=metadata.advisor,
        department_director_signature=_front_value(front, "department_director_signature"),
        needs_review=not (raw_materials and work_content and references),
    )


def task_book_review_items(task: TaskBookModel) -> list[str]:
    if not task.needs_review:
        return []
    missing = []
    if not task.raw_materials_and_requirements:
        missing.append("raw_materials_and_requirements")
    if not task.work_content:
        missing.append("work_content")
    if not task.references:
        missing.append("references")
    return ["task_book_needs_review: missing " + ", ".join(missing)]


def _front_value(front_matter: dict[str, object], *keys: str) -> str:
    for key in keys:
        value = front_matter.get(key)
        if isinstance(value, list):
            value = "\n".join(str(item) for item in value if str(item).strip())
        text = str(value or "").strip()
        if text:
            return text
    return ""

