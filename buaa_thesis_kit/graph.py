from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Literal

from buaa_thesis_kit.models import ThesisModel


GraphStatus = Literal["draft", "pass", "needs_review", "failed"]
GraphNode = Callable[["GraphState"], "NodeResult"]


@dataclass
class NodeResult:
    next_node: str | None


@dataclass
class GraphState:
    source_path: Path
    output_root: Path
    work_dir: Path
    template_path: Path | None = None
    source_kind: str = ""
    extraction_source: Path | None = None
    authoritative_docx: Path | None = None
    model: ThesisModel = field(default_factory=ThesisModel)
    outputs: dict[str, str] = field(default_factory=dict)
    findings: list[str] = field(default_factory=list)
    source_features: dict[str, bool] = field(default_factory=dict)
    repair_actions: list[str] = field(default_factory=list)
    applied_repairs: list[str] = field(default_factory=list)
    blocking_items: list[str] = field(default_factory=list)
    manual_review: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    editability: dict[str, int] = field(default_factory=dict)
    history: list[str] = field(default_factory=list)
    retry_count: int = 0
    max_retries: int = 1
    max_steps: int = 50
    status: GraphStatus = "draft"


class GraphRunner:
    def __init__(self, nodes: dict[str, GraphNode], start_node: str) -> None:
        if start_node not in nodes:
            raise ValueError(f"Unknown start node: {start_node}")
        self.nodes = dict(nodes)
        self.start_node = start_node

    def run(self, state: GraphState) -> GraphState:
        current: str | None = self.start_node
        steps = 0
        while current is not None:
            if steps >= state.max_steps:
                state.blocking_items.append("maximum graph step count exceeded")
                state.status = "failed"
                break
            node = self.nodes.get(current)
            if node is None:
                state.blocking_items.append(f"Unknown graph node: {current}")
                state.status = "failed"
                break

            state.history.append(current)
            steps += 1
            result = node(state)
            next_node = result.next_node
            if next_node == "revise_plan":
                if state.retry_count >= state.max_retries:
                    state.blocking_items.append("maximum graph retry count exceeded")
                    state.status = "failed"
                    break
                state.retry_count += 1
            current = next_node

        if state.status == "failed" or state.blocking_items:
            state.status = "failed"
        elif state.manual_review or any(value == "needs_review" for value in state.outputs.values()):
            state.status = "needs_review"
        else:
            state.status = "pass"
        return state


__all__ = ["GraphRunner", "GraphState", "NodeResult"]
