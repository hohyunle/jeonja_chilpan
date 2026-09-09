from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any
import copy


def snapshot(value: Any) -> Any:
    """Return a safe, displayable copy of an execution value."""

    try:
        return copy.deepcopy(value)
    except Exception:
        return repr(value)


def snapshot_variables(values: dict[str, Any]) -> dict[str, Any]:
    return {name: snapshot(value) for name, value in values.items()}


def display_value(value: Any) -> str:
    """Format values consistently for the visualizer."""

    if isinstance(value, str):
        return repr(value)
    if isinstance(value, bool):
        return "True" if value else "False"
    if value is None:
        return "None"
    return repr(value)


class WorkflowState(str, Enum):
    """Visible application states for the screen-to-visualization workflow."""

    IDLE = "idle"
    SELECTING = "selecting"
    REVIEWING = "reviewing"
    OCR = "ocr"
    EDITING = "editing"
    RUNNING = "running"
    VISUALIZING = "visualizing"


@dataclass(slots=True)
class Diagnostic:
    message: str
    line: int | None = None
    column: int | None = None
    kind: str = "error"

    def format(self) -> str:
        location = ""
        if self.line is not None:
            location = f" (line {self.line}"
            if self.column is not None:
                location += f", column {self.column + 1}"
            location += ")"
        return f"{self.message}{location}"


@dataclass(slots=True)
class TraceStep:
    index: int
    kind: str
    title: str
    line: int | None = None
    source: str = ""
    variables_before: dict[str, Any] = field(default_factory=dict)
    variables_after: dict[str, Any] = field(default_factory=dict)
    details: dict[str, Any] = field(default_factory=dict)
    scope: str = "global"

    def to_display_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "kind": self.kind,
            "title": self.title,
            "line": self.line,
            "source": self.source,
            "variables_before": self.variables_before,
            "variables_after": self.variables_after,
            "details": self.details,
            "scope": self.scope,
        }


@dataclass(slots=True)
class ExecutionTrace:
    code: str
    steps: list[TraceStep] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    error: Diagnostic | None = None
    stopped_reason: str | None = None
    final_variables: dict[str, Any] = field(default_factory=dict)

    @property
    def is_successful(self) -> bool:
        return self.error is None and self.stopped_reason is None

    @property
    def kinds(self) -> set[str]:
        return {step.kind for step in self.steps}


@dataclass(slots=True)
class CodeSegment:
    text: str
    source_label: str = "화면 선택"


@dataclass
class CodeSession:
    """In-memory accumulation for the multi-region selection workflow."""

    segments: list[CodeSegment] = field(default_factory=list)

    @property
    def has_pending(self) -> bool:
        return bool(self.segments)

    @property
    def segment_count(self) -> int:
        return len(self.segments)

    def append(self, text: str, source_label: str = "화면 선택") -> None:
        cleaned = text.replace("\r\n", "\n").replace("\r", "\n").strip("\n")
        if cleaned.strip():
            self.segments.append(CodeSegment(cleaned, source_label))

    def combined_code(self) -> str:
        return "\n".join(segment.text for segment in self.segments)

    def clear(self) -> None:
        self.segments.clear()
