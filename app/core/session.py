from __future__ import annotations

from .models import CodeSession


class SessionController:
    """Coordinates temporary multi-region code selection state."""

    def __init__(self) -> None:
        self.code_session = CodeSession()

    def append_ocr(self, code: str, source_label: str = "화면 선택") -> None:
        self.code_session.append(code, source_label)

    def combined_code(self) -> str:
        return self.code_session.combined_code()

    def reset(self) -> None:
        self.code_session.clear()

