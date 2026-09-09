from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QLabel,
    QPlainTextEdit,
    QVBoxLayout,
)

from app.core.parser import parse_code
from app.ui.theme import code_font, ui_font


class CodeEditor(QPlainTextEdit):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFont(code_font(14))
        self.setTabStopDistance(4 * self.fontMetrics().horizontalAdvance(" "))
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setPlaceholderText("OCR 결과를 확인하거나 Python 코드를 직접 입력하세요.")
        self.setStyleSheet(
            "QPlainTextEdit { background: #ffffff; color: #172c36; "
            "selection-background-color: #dbeaff; selection-color: #172c36; "
            "border: 1px solid #cddbe1; border-radius: 9px; padding: 12px; }"
            "QPlainTextEdit:focus { border: 1px solid #2766cc; }"
        )

    def focus_line(self, line: int | None) -> None:
        if not line or line < 1:
            return
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        cursor.movePosition(QTextCursor.MoveOperation.Down, QTextCursor.MoveMode.MoveAnchor, line - 1)
        self.setTextCursor(cursor)
        self.centerCursor()


class CodeEditorDialog(QDialog):
    def __init__(self, code: str = "", parent=None) -> None:
        super().__init__(parent)
        self.setFont(ui_font(10))
        self.setWindowTitle("코드 확인 및 실행")
        self.setMinimumSize(760, 560)
        self.resize(860, 660)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(10)

        eyebrow = QLabel("CODE REVIEW")
        eyebrow.setObjectName("eyebrow")
        layout.addWidget(eyebrow)
        title = QLabel("코드를 확인하고 실행하세요")
        title.setObjectName("dialogTitle")
        layout.addWidget(title)
        subtitle = QLabel(
            "OCR 결과는 반드시 편집할 수 있습니다. 들여쓰기와 기호를 확인한 뒤 실행하면 교육용 Step이 생성됩니다."
        )
        subtitle.setObjectName("muted")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        editor_frame = QFrame()
        editor_frame.setObjectName("editorFrame")
        editor_layout = QVBoxLayout(editor_frame)
        editor_layout.setContentsMargins(10, 10, 10, 10)
        self.editor = CodeEditor()
        self.editor.setPlainText(code)
        editor_layout.addWidget(self.editor, 1)
        layout.addWidget(editor_frame, 1)

        info_row = QVBoxLayout()
        info_row.setSpacing(4)
        self.validation_label = QLabel()
        self.validation_label.setWordWrap(True)
        info_row.addWidget(self.validation_label)
        syntax_hint = QLabel(
            "지원 문법: 변수·연산 · if/elif/else · for/while · range · print/input · list · 함수/return"
        )
        syntax_hint.setObjectName("muted")
        syntax_hint.setWordWrap(True)
        info_row.addWidget(syntax_hint)
        self.position_label = QLabel("줄 1, 열 1")
        self.position_label.setObjectName("muted")
        info_row.addWidget(self.position_label)
        layout.addLayout(info_row)

        self.editor.cursorPositionChanged.connect(self._update_position)
        self.editor.textChanged.connect(self._validate_code)

        buttons = QDialogButtonBox()
        run_button = buttons.addButton("실행", QDialogButtonBox.ButtonRole.AcceptRole)
        run_button.setObjectName("primary")
        cancel_button = buttons.addButton("취소", QDialogButtonBox.ButtonRole.RejectRole)
        cancel_button.setObjectName("quiet")
        run_button.clicked.connect(self._accept_if_nonempty)
        cancel_button.clicked.connect(self.reject)
        layout.addWidget(buttons)

        self.setStyleSheet(
            "QDialog { background: #f5f7f8; color: #172c36; }"
            "QFrame#editorFrame { background: #e9eff2; border: 1px solid #d5e0e5; border-radius: 11px; }"
            "QLabel#eyebrow { color: #697c87; font-size: 10px; font-weight: 700; letter-spacing: 1px; }"
            "QLabel#dialogTitle { color: #172c36; font-size: 22px; font-weight: 800; }"
            "QLabel#muted { color: #697c87; font-size: 11px; }"
            "QDialogButtonBox QPushButton { min-width: 88px; padding: 9px 14px; border-radius: 8px; "
            "background: #ffffff; color: #172c36; border: 1px solid #cddbe1; font-weight: 600; }"
            "QDialogButtonBox QPushButton:hover { background: #edf4ff; border-color: #8eb2ee; }"
            "QDialogButtonBox QPushButton#primary { background: #2766cc; color: #ffffff; border-color: #2766cc; }"
            "QDialogButtonBox QPushButton#primary:hover { background: #1f57b1; }"
            "QDialogButtonBox QPushButton#quiet { color: #697c87; border-color: transparent; background: transparent; }"
        )
        self.editor.setFocus()
        self._validate_code()

    def _update_position(self) -> None:
        cursor = self.editor.textCursor()
        self.position_label.setText(f"줄 {cursor.blockNumber() + 1}, 열 {cursor.columnNumber() + 1}")

    def _validate_code(self) -> None:
        code = self.editor.toPlainText()
        result = parse_code(code)
        if not code.strip():
            self.validation_label.setText("실행할 코드를 입력하세요.")
            self.validation_label.setStyleSheet("color: #a6600b; font-weight: 600;")
        elif result.ok:
            self.validation_label.setText("✓ 지원 문법 확인됨")
            self.validation_label.setStyleSheet("color: #176c60; font-weight: 600;")
        else:
            self.validation_label.setText(f"⚠ {result.diagnostics[0].format()}")
            self.validation_label.setStyleSheet("color: #b23d47; font-weight: 600;")

    def _accept_if_nonempty(self) -> None:
        if self.editor.toPlainText().strip():
            self.accept()
            return
        self.editor.setFocus()

    def code(self) -> str:
        return self.editor.toPlainText()
