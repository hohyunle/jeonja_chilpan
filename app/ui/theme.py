"""Shared typography for the CodeTrace desktop UI.

The application is distributed to Windows machines with different font
installations, so font families are selected from the fonts available on the
current machine instead of being hard-coded to one name.
"""

from __future__ import annotations

from PySide6.QtGui import QFont, QFontDatabase


_UI_FAMILIES = (
    "Malgun Gothic",
    "맑은 고딕",
    "Noto Sans CJK KR",
    "Noto Sans KR",
    "Yu Gothic UI",
    "Microsoft YaHei UI",
    "Segoe UI",
    "Arial",
)

_CODE_FAMILIES = (
    "Cascadia Code",
    "Consolas",
    "D2Coding",
    "JetBrains Mono",
    "Courier New",
    "Malgun Gothic",
    "맑은 고딕",
)

_installed_families: dict[str, str] | None = None


def _pick_family(candidates: tuple[str, ...], fallback: str) -> str:
    """Return the first installed family, preserving a safe fallback."""

    global _installed_families
    if _installed_families is None:
        try:
            available = QFontDatabase.families()
        except (RuntimeError, TypeError):
            available = []
        if available:
            _installed_families = {
                family.casefold(): family for family in available
            }
    installed = _installed_families or {}
    for candidate in candidates:
        selected = installed.get(candidate.casefold())
        if selected:
            return selected
    return fallback


def ui_font(size: int = 10) -> QFont:
    """Create the Korean-friendly proportional font used by the UI."""

    font = QFont(_pick_family(_UI_FAMILIES, "Arial"))
    font.setStyleHint(QFont.StyleHint.SansSerif)
    font.setPointSize(size)
    return font


def code_font(size: int = 11) -> QFont:
    """Create the legible fixed-width font used for Python and values."""

    font = QFont(_pick_family(_CODE_FAMILIES, "Courier New"))
    font.setStyleHint(QFont.StyleHint.Monospace)
    font.setPointSize(size)
    return font
